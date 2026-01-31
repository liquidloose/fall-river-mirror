/**
 * Gutenberg Document Sidebar Panel for Journalist Custom Fields
 * 
 * This adds a custom panel in the Document sidebar (right side) of Gutenberg
 * that allows editing journalist custom fields directly in the block editor.
 */

(function () {
    const { registerPlugin } = wp.plugins;
    const { PluginDocumentSettingPanel } = wp.editor;
    const { useEntityProp } = wp.coreData;
    const { TextControl, TextareaControl } = wp.components;
    const { __ } = wp.i18n;
    const { useSelect, useDispatch } = wp.data;
    const { useState, useEffect } = wp.element;
    const apiFetch = wp.apiFetch;

    function JournalistMetaPanel() {
        // Only show on journalist post type
        const postType = useSelect((select) =>
            select('core/editor').getCurrentPostType()
        );

        if (postType !== 'journalist') {
            return null;
        }

        const postId = useSelect((select) =>
            select('core/editor').getCurrentPostId()
        );

        // Use local state for meta - we'll save it manually
        const [meta, setMeta] = useState({});
        const [isInitialized, setIsInitialized] = useState(false);
        const [isLoading, setIsLoading] = useState(true);

        // Initialize meta with saved values from REST API when component loads
        useEffect(function () {
            if (!postId || isInitialized) return;

            setIsLoading(true);

            // Fetch the post with meta fields from REST API to initialize
            // console.log('Initializing meta for post:', postId);
            apiFetch({
                path: '/wp/v2/journalist/' + postId + '?context=edit'
            }).then(function (post) {
                // console.log('Fetched post meta:', post.meta);
                // Extract meta fields and ensure all expected fields are initialized
                const metaFields = {
                    _journalist_first_name: '',
                    _journalist_last_name: '',
                    _journalist_email: '',
                    _journalist_phone: '',
                    _journalist_title: '',
                    _journalist_twitter: '',
                    _journalist_linkedin: '',
                    _journalist_bio_short: ''
                };
                if (post.meta) {
                    Object.keys(post.meta).forEach(function (key) {
                        if (key.startsWith('_journalist_')) {
                            metaFields[key] = post.meta[key] || '';
                        }
                    });
                }
                // console.log('Setting initial meta:', metaFields);
                setMeta(metaFields);
                setIsInitialized(true);
                setIsLoading(false);
            }).catch(function (error) {
                console.error('Error fetching journalist meta:', error);
                setIsInitialized(true);
                setIsLoading(false);
            });
        }, [postId, isInitialized]);

        // Hook into save to save meta via REST API
        const isSaving = useSelect(function (select) {
            return select('core/editor').isSavingPost();
        });
        const [wasSaving, setWasSaving] = useState(false);
        const [pendingMeta, setPendingMeta] = useState(null);

        // Save meta when save starts
        useEffect(function () {
            if (!wasSaving && isSaving && postId && isInitialized) {
                // Only save if we have meta data
                if (!meta || Object.keys(meta).length === 0) {
                    setWasSaving(isSaving);
                    return;
                }

                // Save meta fields via REST API
                // WordPress REST API expects meta in a 'meta' object
                // console.log('Saving meta:', JSON.stringify(meta, null, 2));
                setPendingMeta(meta);

                // Send meta in the correct format for WordPress REST API
                apiFetch({
                    path: '/wp/v2/journalist/' + postId,
                    method: 'POST',
                    data: {
                        meta: meta
                    }
                }).then(function (response) {
                    // console.log('Meta saved successfully. Response meta:', JSON.stringify(response.meta, null, 2));
                    setPendingMeta(null);
                }).catch(function (error) {
                    console.error('Error saving journalist meta:', error);
                    // console.error('Error details:', error.message, error.data);
                    setPendingMeta(null);
                });
            }
            setWasSaving(isSaving);
        }, [isSaving, postId, wasSaving, meta, isInitialized]);

        // Refresh after save completes
        useEffect(function () {
            if (wasSaving && !isSaving && postId && pendingMeta === null) {
                setTimeout(function () {
                    // console.log('Refreshing meta after save...');
                    apiFetch({
                        path: '/wp/v2/journalist/' + postId + '?context=edit'
                    }).then(function (post) {
                        // console.log('Refreshed post meta:', JSON.stringify(post.meta, null, 2));
                        const metaFields = {
                            _journalist_first_name: '',
                            _journalist_last_name: '',
                            _journalist_email: '',
                            _journalist_phone: '',
                            _journalist_title: '',
                            _journalist_twitter: '',
                            _journalist_linkedin: '',
                            _journalist_bio_short: ''
                        };
                        if (post.meta) {
                            Object.keys(post.meta).forEach(function (key) {
                                if (key.startsWith('_journalist_')) {
                                    metaFields[key] = post.meta[key] || '';
                                }
                            });
                        }
                        // console.log('Setting refreshed meta:', JSON.stringify(metaFields, null, 2));
                        setMeta(metaFields);
                    }).catch(function (error) {
                        console.error('Error refreshing meta:', error);
                    });
                }, 500);
            }
        }, [isSaving, wasSaving, postId, pendingMeta]);

        // Show loading state while fetching initial data
        if (isLoading) {
            return wp.element.createElement(
                PluginDocumentSettingPanel,
                {
                    name: 'journalist-information',
                    title: __('Journalist Information', 'fall-river-mirror'),
                    className: 'journalist-meta-panel'
                },
                wp.element.createElement('p', {}, __('Loading...', 'fall-river-mirror'))
            );
        }

        return wp.element.createElement(
            PluginDocumentSettingPanel,
            {
                name: 'journalist-information',
                title: __('Journalist Information', 'fall-river-mirror'),
                className: 'journalist-meta-panel'
            },
            // Name field removed - using post title instead
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('First Name', 'fall-river-mirror'),
                value: (meta && meta._journalist_first_name) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_first_name: value || '' })
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('Last Name', 'fall-river-mirror'),
                value: (meta && meta._journalist_last_name) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_last_name: value || '' })
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('Email', 'fall-river-mirror'),
                type: 'email',
                value: (meta && meta._journalist_email) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_email: value || '' })
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('Phone', 'fall-river-mirror'),
                value: (meta && meta._journalist_phone) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_phone: value || '' })
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('Title/Position', 'fall-river-mirror'),
                value: (meta && meta._journalist_title) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_title: value || '' }),
                help: __('e.g., Senior Reporter, Editor, etc.', 'fall-river-mirror')
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('Twitter/X', 'fall-river-mirror'),
                value: (meta && meta._journalist_twitter) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_twitter: value || '' }),
                placeholder: '@username'
            }),
            wp.element.createElement(TextControl, {
                __next40pxDefaultSize: true,
                label: __('LinkedIn', 'fall-river-mirror'),
                type: 'url',
                value: (meta && meta._journalist_linkedin) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_linkedin: value || '' }),
                placeholder: 'https://linkedin.com/in/...'
            }),
            wp.element.createElement(TextareaControl, {
                __nextHasNoMarginBottom: true,
                label: __('Short Bio', 'fall-river-mirror'),
                value: (meta && meta._journalist_bio_short) || '',
                onChange: (value) => setMeta({ ...(meta || {}), _journalist_bio_short: value || '' }),
                help: __('A brief bio or tagline for the journalist.', 'fall-river-mirror'),
                rows: 3
            })
        );
    }

    registerPlugin('journalist-meta-panel', {
        render: JournalistMetaPanel,
        icon: 'admin-users'
    });
})();

