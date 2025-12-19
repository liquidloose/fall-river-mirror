/**
 * Gutenberg Document Sidebar Panel for Article Custom Fields
 * 
 * This file creates a custom panel in the WordPress Gutenberg block editor's
 * Document sidebar (right side panel) that allows editing article custom fields
 * directly within the editor interface.
 * 
 * HOW IT WORKS:
 * 1. Registers a plugin that renders a custom panel in the Document sidebar
 * 2. Only displays when editing an 'article' post type
 * 3. Fetches article meta fields and available journalists from the REST API
 * 4. Provides UI controls (text inputs, textareas, checkboxes) for editing meta fields
 * 5. Automatically saves meta fields when the post is saved via WordPress's save hook
 * 6. Refreshes data after save to ensure UI reflects saved state
 * 
 * DATA FLOW:
 * - On load: Fetches journalists list + current article meta from REST API
 * - On edit: Updates local React state (doesn't save yet)
 * - On save: WordPress triggers save → useEffect hook intercepts → saves via REST API
 * - After save: Refreshes data from REST API to sync UI with database
 * 
 * @package FallRiverMirror
 */

(function () {
    // Import WordPress Gutenberg components and utilities
    const { registerPlugin } = wp.plugins;           // Plugin registration system
    const { PluginDocumentSettingPanel } = wp.editor; // Panel component for Document sidebar
    const { CheckboxControl, TextControl, TextareaControl } = wp.components; // Form controls
    const { __ } = wp.i18n;                          // Translation function
    const { useSelect } = wp.data;                   // React hook to access WordPress data store
    const { useState, useEffect } = wp.element;      // React hooks for state and side effects
    const apiFetch = wp.apiFetch;                    // WordPress REST API fetch utility

    /**
     * ArticleMetaPanel Component
     * 
     * Main React component that renders the custom meta fields panel.
     * This component manages all the state and UI for editing article custom fields.
     */
    function ArticleMetaPanel() {
        /**
         * POST TYPE CHECK
         * 
         * Only show this panel when editing an 'article' post type.
         * useSelect is a React hook that subscribes to WordPress's data store.
         * It will re-render whenever the post type changes.
         */
        const postType = useSelect((select) =>
            select('core/editor').getCurrentPostType()
        );

        // Early return if not an article - panel won't render
        if (postType !== 'article') {
            return null;
        }

        /**
         * GET CURRENT POST ID
         * 
         * Retrieves the ID of the post currently being edited.
         * Needed for fetching and saving meta data.
         */
        const postId = useSelect((select) =>
            select('core/editor').getCurrentPostId()
        );

        /**
         * REACT STATE MANAGEMENT
         * 
         * useState hooks manage component state:
         * - selectedJournalists: Array of journalist post IDs currently selected for this article
         * - allJournalists: Array of all available journalist posts (for the checkbox list)
         * - meta: Object containing all article meta field values (_article_content, _article_committee, etc.)
         * - isLoading: Boolean flag to show loading state while fetching data
         * - isInitialized: Boolean flag to prevent duplicate API calls
         */
        const [selectedJournalists, setSelectedJournalists] = useState([]);
        const [allJournalists, setAllJournalists] = useState([]);
        const [meta, setMeta] = useState({});
        const [isLoading, setIsLoading] = useState(true);
        const [isInitialized, setIsInitialized] = useState(false);

        /**
         * INITIAL DATA FETCH
         * 
         * useEffect hook runs when component mounts or when dependencies change.
         * This fetches:
         * 1. All available journalists (for the checkbox list)
         * 2. Current article data including meta fields and selected journalists
         * 
         * Dependencies: [postId, isInitialized]
         * - Runs when postId changes (switching articles)
         * - isInitialized prevents re-fetching on every render
         * 
         * API ENDPOINTS USED:
         * - GET /wp/v2/journalist - Fetches all journalists
         * - GET /wp/v2/article/{id}?context=edit - Fetches current article with meta
         */
        useEffect(function () {
            // Guard: Don't fetch if no post ID or already initialized
            if (!postId || isInitialized) return;

            setIsLoading(true);

            // STEP 1: Fetch all available journalists
            // This populates the checkbox list so users can select which journalists
            // are associated with this article
            apiFetch({
                path: '/wp/v2/journalist?per_page=100&orderby=title&order=asc'
            }).then(function (journalists) {
                // Store all journalists in state for rendering checkboxes
                setAllJournalists(journalists);

                // STEP 2: Fetch current article data
                // context=edit ensures we get all meta fields (not just public ones)
                return apiFetch({
                    path: '/wp/v2/article/' + postId + '?context=edit'
                });
            }).then(function (article) {
                /**
                 * EXTRACT JOURNALIST SELECTIONS
                 * 
                 * The _article_journalists meta field stores an array of journalist post IDs.
                 * This extracts that array and ensures it's always an array (never null/undefined).
                 */
                const journalists = article.meta && article.meta._article_journalists
                    ? article.meta._article_journalists
                    : [];
                setSelectedJournalists(Array.isArray(journalists) ? journalists : []);

                /**
                 * EXTRACT META FIELDS
                 * 
                 * Extract all article meta fields from the API response.
                 * Each field is prefixed with '_article_' in the database.
                 * Default values are set for empty fields:
                 * - String fields default to empty string ''
                 * - view_count defaults to 0 (integer)
                 */
                const metaFields = {};
                if (article.meta) {
                    metaFields._article_content = article.meta._article_content || '';
                    metaFields._article_committee = article.meta._article_committee || '';
                    metaFields._article_youtube_id = article.meta._article_youtube_id || '';
                    metaFields._article_bullet_points = article.meta._article_bullet_points || '';
                    metaFields._article_meeting_date = article.meta._article_meeting_date || '';
                    metaFields._article_view_count = article.meta._article_view_count || 0;
                }
                setMeta(metaFields);
                
                // Mark as initialized to prevent duplicate fetches
                setIsInitialized(true);
                setIsLoading(false);
            }).catch(function (error) {
                // Error handling: Log error and stop loading state
                console.error('Error fetching article/journalist data:', error);
                setIsLoading(false);
                setIsInitialized(true);
            });
        }, [postId, isInitialized]);

        /**
         * SAVE HOOK - INTERCEPT WORDPRESS SAVE
         * 
         * This useEffect hook watches WordPress's save state and automatically
         * saves all meta fields to the database when the user clicks "Save" or "Update".
         * 
         * HOW IT WORKS:
         * 1. WordPress triggers save → isSaving becomes true
         * 2. This hook detects the transition from false → true
         * 3. Sends all current state (journalists + meta fields) to REST API
         * 4. WordPress continues with its normal save process
         * 
         * WHY THIS APPROACH:
         * - WordPress doesn't automatically save custom meta fields
         * - We need to intercept the save action and manually persist our data
         * - Using REST API ensures data is saved correctly with proper validation
         * 
         * Dependencies track all state that needs to be saved
         */
        const isSaving = useSelect(function (select) {
            return select('core/editor').isSavingPost();
        });
        const [wasSaving, setWasSaving] = useState(false);
        const [pendingJournalists, setPendingJournalists] = useState(null);

        useEffect(function () {
            /**
             * SAVE TRIGGER CONDITION
             * 
             * Only save when:
             * - Save just started (wasSaving=false, isSaving=true)
             * - We have a post ID
             * - Data has been initialized (prevents saving before data loads)
             */
            if (!wasSaving && isSaving && postId && isInitialized) {
                // Store current journalist selection for the refresh hook
                setPendingJournalists(selectedJournalists);

                /**
                 * SAVE ALL META FIELDS VIA REST API
                 * 
                 * POST to /wp/v2/article/{id} with meta object containing:
                 * - _article_journalists: Array of journalist IDs
                 * - _article_content: HTML content string
                 * - _article_committee: Committee name string
                 * - _article_youtube_id: YouTube video ID string
                 * - _article_bullet_points: Bullet points text string
                 * - _article_meeting_date: Date string
                 * - _article_view_count: Integer count
                 * 
                 * WordPress REST API automatically validates and saves these meta fields
                 * based on the registration in article-post-type.php
                 */
                apiFetch({
                    path: '/wp/v2/article/' + postId,
                    method: 'POST',
                    data: {
                        meta: {
                            _article_journalists: selectedJournalists,
                            _article_content: (meta && meta._article_content) || '',
                            _article_committee: (meta && meta._article_committee) || '',
                            _article_youtube_id: (meta && meta._article_youtube_id) || '',
                            _article_bullet_points: (meta && meta._article_bullet_points) || '',
                            _article_meeting_date: (meta && meta._article_meeting_date) || '',
                            _article_view_count: (meta && meta._article_view_count) || 0
                        }
                    }
                }).then(function (response) {
                    // Save successful - clear pending flag
                    setPendingJournalists(null);
                }).catch(function (error) {
                    // Save failed - log error but don't block WordPress save
                    console.error('Error saving article meta:', error);
                    setPendingJournalists(null);
                });
            }
            // Track previous save state for transition detection
            setWasSaving(isSaving);
        }, [isSaving, postId, wasSaving, selectedJournalists, meta, isInitialized]);

        /**
         * REFRESH AFTER SAVE
         * 
         * After WordPress finishes saving, refresh the data from the database.
         * This ensures the UI reflects any server-side processing or validation
         * that might have modified the data.
         * 
         * WHY NEEDED:
         * - Server might sanitize/transform data
         * - Other plugins might modify meta fields
         * - Ensures UI shows exactly what's in the database
         */
        useEffect(function () {
            // Only refresh when save completes (wasSaving=true, isSaving=false)
            // and save was successful (pendingJournalists === null)
            if (wasSaving && !isSaving && postId && pendingJournalists === null) {
                // Small delay to ensure database write is complete
                setTimeout(function () {
                    apiFetch({
                        path: '/wp/v2/article/' + postId + '?context=edit'
                    }).then(function (article) {
                        // Refresh journalist selections
                        const journalists = article.meta && article.meta._article_journalists
                            ? article.meta._article_journalists
                            : [];
                        setSelectedJournalists(Array.isArray(journalists) ? journalists : []);

                        // Refresh all meta fields from database
                        const metaFields = {};
                        if (article.meta) {
                            metaFields._article_content = article.meta._article_content || '';
                            metaFields._article_committee = article.meta._article_committee || '';
                            metaFields._article_youtube_id = article.meta._article_youtube_id || '';
                            metaFields._article_bullet_points = article.meta._article_bullet_points || '';
                            metaFields._article_meeting_date = article.meta._article_meeting_date || '';
                            metaFields._article_view_count = article.meta._article_view_count || 0;
                        }
                        setMeta(metaFields);
                    }).catch(function (error) {
                        console.error('Error refreshing article meta:', error);
                    });
                }, 500); // 500ms delay to ensure database write completes
            }
        }, [isSaving, wasSaving, postId, pendingJournalists]);

        /**
         * JOURNALIST CHECKBOX HANDLER
         * 
         * Called when user checks/unchecks a journalist checkbox.
         * Updates the selectedJournalists array in state.
         * 
         * @param {number} journalistId - The post ID of the journalist
         * @param {boolean} isChecked - Whether the checkbox is now checked
         */
        const handleJournalistChange = function (journalistId, isChecked) {
            if (isChecked) {
                // Add journalist ID to selection array
                setSelectedJournalists([...selectedJournalists, journalistId]);
            } else {
                // Remove journalist ID from selection array using filter
                setSelectedJournalists(selectedJournalists.filter(function (id) {
                    return id !== journalistId;
                }));
            }
        };

        /**
         * LOADING STATE
         * 
         * Show loading message while fetching initial data.
         * Prevents UI from rendering with empty/incorrect data.
         */
        if (isLoading) {
            return wp.element.createElement(
                PluginDocumentSettingPanel,
                {
                    name: 'article-information',
                    title: __('Article Information', 'fall-river-mirror'),
                    className: 'article-meta-panel'
                },
                wp.element.createElement('p', {}, __('Loading...', 'fall-river-mirror'))
            );
        }

        /**
         * BUILD PANEL UI
         * 
         * Construct the panel content as an array of React elements.
         * This allows conditional rendering of sections.
         */
        const panelChildren = [];

        /**
         * JOURNALISTS SECTION
         * 
         * Renders checkboxes for selecting journalists associated with this article.
         * Only shows if there are journalists available in the system.
         * 
         * UI STRUCTURE:
         * - Section title: "Journalist(s)"
         * - Checkbox for each journalist (showing their name/title)
         * - Checked state reflects selectedJournalists array
         */
        if (allJournalists.length > 0) {
            panelChildren.push(
                wp.element.createElement('div', { key: 'journalists-section', style: { marginBottom: '16px' } },
                    wp.element.createElement('strong', { style: { display: 'block', marginBottom: '8px' } }, __('Journalist(s)', 'fall-river-mirror')),
                    // Map over all journalists and create a checkbox for each
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
                )
            );
        } else {
            // Show message if no journalists exist
            panelChildren.push(
                wp.element.createElement('p', { key: 'no-journalists' }, __('No journalists found.', 'fall-river-mirror'))
            );
        }

        /**
         * RENDER MAIN PANEL
         * 
         * Returns the PluginDocumentSettingPanel component with all form controls.
         * panelChildren.concat() adds the journalists section to the meta field controls.
         * 
         * META FIELD CONTROLS:
         * Each field uses a React component (TextControl, TextareaControl) that:
         * - Displays current value from meta state
         * - Updates meta state on change (via onChange handler)
         * - State changes trigger re-render, but don't save until post is saved
         */
        return wp.element.createElement(
            PluginDocumentSettingPanel,
            {
                name: 'article-information',
                title: __('Article Information', 'fall-river-mirror'),
                className: 'article-meta-panel'
            },
            panelChildren.concat([
                /**
                 * CONTENT FIELD
                 * 
                 * Large textarea for HTML content.
                 * This is the main article content stored in _article_content meta.
                 * Manually handled (not auto-generated by WordPress REST API registration).
                 */
                wp.element.createElement(TextareaControl, {
                    key: 'article_content',
                    label: __('Content', 'fall-river-mirror'),
                    value: (meta && meta._article_content) || '',
                    onChange: function (value) {
                        // Update meta state with new content value
                        setMeta({ ...(meta || {}), _article_content: value || '' });
                    },
                    rows: 8
                }),
                /**
                 * COMMITTEE FIELD
                 * 
                 * Single-line text input for committee name.
                 */
                wp.element.createElement(TextControl, {
                    key: 'committee',
                    label: __('Committee', 'fall-river-mirror'),
                    value: (meta && meta._article_committee) || '',
                    onChange: function (value) {
                        setMeta({ ...(meta || {}), _article_committee: value || '' });
                    }
                }),
                /**
                 * YOUTUBE ID FIELD
                 * 
                 * Single-line text input for YouTube video ID.
                 * Placeholder provides example format.
                 */
                wp.element.createElement(TextControl, {
                    key: 'youtube-id',
                    label: __('YouTube ID', 'fall-river-mirror'),
                    value: (meta && meta._article_youtube_id) || '',
                    onChange: function (value) {
                        setMeta({ ...(meta || {}), _article_youtube_id: value || '' });
                    },
                    placeholder: 'e.g., dQw4w9WgXcQ'
                }),
                /**
                 * BULLET POINTS FIELD
                 * 
                 * Multi-line textarea for key points or summary.
                 * Help text explains the field's purpose.
                 */
                wp.element.createElement(TextareaControl, {
                    key: 'bullet-points',
                    label: __('Bullet Points', 'fall-river-mirror'),
                    value: (meta && meta._article_bullet_points) || '',
                    onChange: function (value) {
                        setMeta({ ...(meta || {}), _article_bullet_points: value || '' });
                    },
                    help: __('Key points or summary of the article.', 'fall-river-mirror'),
                    rows: 4
                }),
                /**
                 * MEETING DATE FIELD
                 * 
                 * Date input (type="date") for meeting date.
                 * Browser provides native date picker.
                 */
                wp.element.createElement(TextControl, {
                    key: 'meeting-date',
                    label: __('Meeting Date', 'fall-river-mirror'),
                    type: 'date',
                    value: (meta && meta._article_meeting_date) || '',
                    onChange: function (value) {
                        setMeta({ ...(meta || {}), _article_meeting_date: value || '' });
                    }
                }),
                /**
                 * VIEW COUNT FIELD
                 * 
                 * Number input (type="number") for view count.
                 * onChange parses value as integer to ensure numeric type.
                 * Defaults to 0 if empty or invalid.
                 */
                wp.element.createElement(TextControl, {
                    key: 'view-count',
                    label: __('View Count', 'fall-river-mirror'),
                    type: 'number',
                    value: (meta && meta._article_view_count) || 0,
                    onChange: function (value) {
                        // Parse as integer to ensure numeric type in state
                        setMeta({ ...(meta || {}), _article_view_count: parseInt(value) || 0 });
                    },
                    help: __('Number of views for the associated video.', 'fall-river-mirror')
                })
            ])
        );
    }

    /**
     * REGISTER PLUGIN
     * 
     * Registers this component as a Gutenberg plugin.
     * This makes it available in the editor and WordPress will render it
     * in the Document sidebar automatically.
     * 
     * @param {string} 'article-meta-panel' - Unique plugin identifier
     * @param {object} { render: ArticleMetaPanel, icon: 'admin-users' }
     *   - render: The React component to render
     *   - icon: Dashicon name for the panel (if shown in plugin menu)
     */
    registerPlugin('article-meta-panel', {
        render: ArticleMetaPanel,
        icon: 'admin-users'
    });
})();