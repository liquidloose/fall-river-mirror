/**
 * Gutenberg Document Sidebar Panel for Article Custom Fields
 * 
 * This adds a custom panel in the Document sidebar (right side) of Gutenberg
 * that allows selecting journalists for an article directly in the block editor.
 */

(function () {
    const { registerPlugin } = wp.plugins;
    const { PluginDocumentSettingPanel } = wp.editor;
    const { CheckboxControl } = wp.components;
    const { __ } = wp.i18n;
    const { useSelect } = wp.data;
    const { useState, useEffect } = wp.element;
    const apiFetch = wp.apiFetch;

    function ArticleMetaPanel() {
        // Only show on article post type
        const postType = useSelect((select) =>
            select('core/editor').getCurrentPostType()
        );

        if (postType !== 'article') {
            return null;
        }

        const postId = useSelect((select) =>
            select('core/editor').getCurrentPostId()
        );

        // State for selected journalist IDs
        const [selectedJournalists, setSelectedJournalists] = useState([]);
        // State for all available journalists
        const [allJournalists, setAllJournalists] = useState([]);
        const [isLoading, setIsLoading] = useState(true);
        const [isInitialized, setIsInitialized] = useState(false);

        // Fetch all journalists and current selection
        useEffect(function () {
            if (!postId || isInitialized) return;

            setIsLoading(true);

            // Fetch all journalists
            apiFetch({
                path: '/wp/v2/journalist?per_page=100&orderby=title&order=asc'
            }).then(function (journalists) {
                setAllJournalists(journalists);

                // Fetch current article to get selected journalists
                return apiFetch({
                    path: '/wp/v2/article/' + postId + '?context=edit'
                });
            }).then(function (article) {
                // Get selected journalist IDs from meta
                const journalists = article.meta && article.meta._article_journalists
                    ? article.meta._article_journalists
                    : [];
                setSelectedJournalists(Array.isArray(journalists) ? journalists : []);
                setIsInitialized(true);
                setIsLoading(false);
            }).catch(function (error) {
                console.error('Error fetching article/journalist data:', error);
                setIsLoading(false);
                setIsInitialized(true);
            });
        }, [postId, isInitialized]);

        // Hook into save to save journalists via REST API
        const isSaving = useSelect(function (select) {
            return select('core/editor').isSavingPost();
        });
        const [wasSaving, setWasSaving] = useState(false);
        const [pendingJournalists, setPendingJournalists] = useState(null);

        // Save journalists when save starts
        useEffect(function () {
            if (!wasSaving && isSaving && postId && isInitialized) {
                // Save journalists via REST API
                setPendingJournalists(selectedJournalists);

                apiFetch({
                    path: '/wp/v2/article/' + postId,
                    method: 'POST',
                    data: {
                        meta: {
                            _article_journalists: selectedJournalists
                        }
                    }
                }).then(function (response) {
                    setPendingJournalists(null);
                }).catch(function (error) {
                    console.error('Error saving article journalists:', error);
                    setPendingJournalists(null);
                });
            }
            setWasSaving(isSaving);
        }, [isSaving, postId, wasSaving, selectedJournalists, isInitialized]);

        // Refresh after save completes
        useEffect(function () {
            if (wasSaving && !isSaving && postId && pendingJournalists === null) {
                setTimeout(function () {
                    apiFetch({
                        path: '/wp/v2/article/' + postId + '?context=edit'
                    }).then(function (article) {
                        const journalists = article.meta && article.meta._article_journalists
                            ? article.meta._article_journalists
                            : [];
                        setSelectedJournalists(Array.isArray(journalists) ? journalists : []);
                    }).catch(function (error) {
                        console.error('Error refreshing article journalists:', error);
                    });
                }, 500);
            }
        }, [isSaving, wasSaving, postId, pendingJournalists]);

        // Handle checkbox change
        const handleJournalistChange = function (journalistId, isChecked) {
            if (isChecked) {
                // Add journalist ID to selection
                setSelectedJournalists([...selectedJournalists, journalistId]);
            } else {
                // Remove journalist ID from selection
                setSelectedJournalists(selectedJournalists.filter(function (id) {
                    return id !== journalistId;
                }));
            }
        };

        if (isLoading) {
            return wp.element.createElement(
                PluginDocumentSettingPanel,
                {
                    name: 'article-journalists',
                    title: __('Article Journalists', 'fall-river-mirror'),
                    className: 'article-meta-panel'
                },
                wp.element.createElement('p', {}, __('Loading journalists...', 'fall-river-mirror'))
            );
        }

        if (allJournalists.length === 0) {
            return wp.element.createElement(
                PluginDocumentSettingPanel,
                {
                    name: 'article-journalists',
                    title: __('Article Journalists', 'fall-river-mirror'),
                    className: 'article-meta-panel'
                },
                wp.element.createElement('p', {}, __('No journalists found.', 'fall-river-mirror'))
            );
        }

        return wp.element.createElement(
            PluginDocumentSettingPanel,
            {
                name: 'article-journalists',
                title: __('Article Journalists', 'fall-river-mirror'),
                className: 'article-meta-panel'
            },
            allJournalists.map(function (journalist) {
                const isChecked = selectedJournalists.indexOf(journalist.id) !== -1;
                return wp.element.createElement(CheckboxControl, {
                    key: journalist.id,
                    label: journalist.title.rendered || journalist.title.raw,
                    checked: isChecked,
                    onChange: function (checked) {
                        handleJournalistChange(journalist.id, checked);
                    }
                });
            })
        );
    }

    registerPlugin('article-meta-panel', {
        render: ArticleMetaPanel,
        icon: 'admin-users'
    });
})();

