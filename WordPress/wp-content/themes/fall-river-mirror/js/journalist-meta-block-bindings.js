/**
 * Block Bindings UI for Journalist Meta Fields
 * 
 * This file adds a user interface in the Gutenberg block editor that allows users
 * to bind blocks (Paragraph, Heading, HTML) to journalist meta fields. When a block
 * is bound, it will automatically display the value from the journalist's meta field
 * on the frontend.
 * 
 * WHAT IT DOES:
 * - Adds a dropdown menu in the block settings sidebar when editing journalist posts
 * - Allows selecting which journalist meta field to bind to (first_name, last_name, etc.)
 * - Sets up the binding configuration so WordPress knows where to get the data
 * - Only appears for blocks that support content bindings (Paragraph, Heading, HTML)
 * - Only appears when editing journalist post types
 * 
 * USER FLOW:
 * 1. User edits a journalist post
 * 2. User adds a Paragraph, Heading, or HTML block
 * 3. User opens block settings sidebar
 * 4. User sees "Journalist Meta Binding" panel
 * 5. User selects a meta field from dropdown (e.g., "First Name")
 * 6. Block is now bound - will display that meta field's value on frontend
 */

(function () {
    // Import WordPress editor components needed for the UI
    const { select } = wp.data;
    const { addFilter } = wp.hooks;
    const { InspectorControls } = wp.blockEditor;
    const { PanelBody, SelectControl, TextControl } = wp.components;
    const { useSelect } = wp.data;
    const { createElement: el, useEffect } = wp.element;
    const { __ } = wp.i18n;
    const { apiFetch } = wp;
    
    /**
     * STEP 1: REGISTER BLOCK EDITOR FILTER
     * 
     * Hooks into WordPress's block editor to modify how blocks are rendered in the editor.
     * This allows us to add our custom UI panel to the block settings sidebar.
     */
    addFilter(
        'editor.BlockEdit',
        'fr-mirror/journalist-meta-bindings',
        function(BlockEdit) {
            /**
             * STEP 2: CREATE ENHANCED BLOCK COMPONENT
             * 
             * Returns a new component that wraps the original block editor component.
             * This wrapper adds our custom binding UI while preserving all original block functionality.
             */
            return function(props) {
                /**
                 * STEP 3: CHECK POST TYPE
                 * 
                 * Only show binding controls when editing journalist post types.
                 * If not a journalist, return the original block component unchanged.
                 */
                const postType = useSelect(function(select) {
                    return select('core/editor').getCurrentPostType();
                }, []);
                
                if (postType !== 'journalist') {
                    return el(BlockEdit, props);
                }
                
                /**
                 * STEP 4: CHECK BLOCK TYPE
                 * 
                 * Only show binding controls for blocks that support content bindings.
                 * Currently supports: Paragraph, Heading, and HTML blocks.
                 * Other blocks return unchanged.
                 */
                const blockName = props.name;
                const supportsContent = ['core/paragraph', 'core/heading', 'core/html'].includes(blockName);
                
                if (!supportsContent) {
                    return el(BlockEdit, props);
                }
                
                /**
                 * STEP 5: CHECK EXISTING BINDINGS
                 * 
                 * Check if this block already has a binding configured.
                 * If it does, we'll show the current selection in the dropdown.
                 */
                const bindings = props.attributes.metadata?.bindings || {};
                const contentBinding = bindings.content;
                const isBound = contentBinding?.source === 'fr-mirror/journalist-meta';
                const fieldKey = isBound ? contentBinding?.args?.key : null;
                
                // Debug logging
                if (window.location.search.includes('debug=1')) {
                    console.log('Block binding state:', {
                        bindings: bindings,
                        contentBinding: contentBinding,
                        isBound: isBound,
                        fieldKey: fieldKey,
                        allAttributes: props.attributes
                    });
                }
                
                /**
                 * STEP 5A: GET POST ID AND META
                 * 
                 * Fetch the post ID and current meta values so we can display
                 * the actual content in the editor.
                 */
                const postId = useSelect(function(select) {
                    return select('core/editor').getCurrentPostId();
                }, []);
                
                const meta = useSelect(function(select) {
                    return select('core/editor').getEditedPostAttribute('meta');
                }, []);
                
                /**
                 * STEP 5B: UPDATE WHEN META CHANGES
                 * 
                 * WordPress automatically resolves block bindings via PHP registration.
                 * We just need to update the block content when meta changes in the sidebar.
                 */
                useEffect(function() {
                    if (!isBound || !fieldKey || !meta) {
                        return;
                    }
                    
                    // Construct meta key: '_journalist_' + field_key
                    const metaKey = '_journalist_' + fieldKey;
                    const value = meta[metaKey] || '';
                    
                    // Update block content when meta changes
                    if (props.attributes.content !== value) {
                        props.setAttributes({
                            content: value
                        });
                    }
                }, [meta, isBound, fieldKey]);
                
                /**
                 * STEP 6: RENDER BLOCK WITH BINDING UI
                 * 
                 * Returns the original block editor component plus our custom panel
                 * in the InspectorControls (block settings sidebar).
                 */
                return el(
                    'div',
                    {},
                    // Original block editor component (unchanged)
                    el(BlockEdit, props),
                    // Our custom panel in the block settings sidebar
                    el(
                        InspectorControls,
                        {},
                        el(
                            PanelBody,
                            {
                                title: __('Journalist Meta Binding', 'fr-mirror'),
                                initialOpen: isBound
                            },
                            /**
                             * STEP 7: SHOW CURRENT BINDING STATUS
                             * 
                             * Display which field is currently bound (if any) so user
                             * can see the selection clearly.
                             */
                            isBound && fieldKey ? el('div', {
                                style: { 
                                    marginBottom: '16px',
                                    padding: '8px',
                                    backgroundColor: '#f0f0f1',
                                    borderRadius: '2px',
                                    fontSize: '13px'
                                }
                            }, el('strong', {}, __('Currently bound to: ', 'fr-mirror')), 
                                el('span', {}, 
                                    fieldKey === 'first_name' ? __('First Name', 'fr-mirror') :
                                    fieldKey === 'last_name' ? __('Last Name', 'fr-mirror') :
                                    fieldKey === 'email' ? __('Email', 'fr-mirror') :
                                    fieldKey === 'phone' ? __('Phone', 'fr-mirror') :
                                    fieldKey === 'title' ? __('Title/Position', 'fr-mirror') :
                                    fieldKey === 'twitter' ? __('Twitter/X', 'fr-mirror') :
                                    fieldKey === 'linkedin' ? __('LinkedIn', 'fr-mirror') :
                                    fieldKey === 'bio_short' ? __('Short Bio', 'fr-mirror') :
                                    fieldKey
                                )
                            ) : null,
                            /**
                             * STEP 8: BINDING SELECTION DROPDOWN
                             * 
                             * Dropdown menu that lets users select which journalist meta field
                             * to bind this block to. Options include all available meta fields.
                             */
                            el(SelectControl, {
                                __nextHasNoMarginBottom: true,
                                label: __('Bind to Journalist Meta', 'fr-mirror'),
                                value: isBound ? contentBinding?.args?.key || '' : '',
                                options: [
                                    { label: __('None', 'fr-mirror'), value: '' },
                                    { label: __('First Name', 'fr-mirror'), value: 'first_name' },
                                    { label: __('Last Name', 'fr-mirror'), value: 'last_name' },
                                    { label: __('Email', 'fr-mirror'), value: 'email' },
                                    { label: __('Phone', 'fr-mirror'), value: 'phone' },
                                    { label: __('Title/Position', 'fr-mirror'), value: 'title' },
                                    { label: __('Twitter/X', 'fr-mirror'), value: 'twitter' },
                                    { label: __('LinkedIn', 'fr-mirror'), value: 'linkedin' },
                                    { label: __('Short Bio', 'fr-mirror'), value: 'bio_short' }
                                ],
                                /**
                                 * STEP 9: HANDLE BINDING SELECTION
                                 * 
                                 * When user selects a meta field from the dropdown:
                                 * - If a field is selected: Creates binding configuration
                                 * - If "None" is selected: Removes binding configuration
                                 * 
                                 * The binding configuration tells WordPress:
                                 * - Source: 'fr-mirror/journalist-meta' (our custom binding source)
                                 * - Key: Which meta field to use (first_name, last_name, etc.)
                                 */
                                onChange: function(value) {
                                    const { setAttributes } = props;
                                    const currentMetadata = props.attributes.metadata || {};
                                    const currentBindings = currentMetadata.bindings || {};
                                    
                                    if (value) {
                                        /**
                                         * STEP 8A: CREATE BINDING
                                         * 
                                         * User selected a meta field. We:
                                         * 1. Create binding configuration in block metadata
                                         * 2. Store the source ('fr-mirror/journalist-meta') and key (field name)
                                         * 3. Actual content will be fetched and displayed by useEffect hooks above
                                         */
                                        const newBinding = {
                                            source: 'fr-mirror/journalist-meta',
                                            args: {
                                                key: value
                                            }
                                        };
                                        
                                        setAttributes({
                                            metadata: {
                                                ...currentMetadata,
                                                bindings: {
                                                    ...currentBindings,
                                                    content: newBinding
                                                }
                                            }
                                        });
                                    } else {
                                        /**
                                         * STEP 8B: REMOVE BINDING
                                         * 
                                         * User selected "None". We:
                                         * 1. Remove binding configuration from block metadata
                                         * 2. Block returns to normal editable state
                                         */
                                        const newBindings = { ...currentBindings };
                                        delete newBindings.content;
                                        setAttributes({
                                            metadata: {
                                                ...currentMetadata,
                                                bindings: Object.keys(newBindings).length > 0 ? newBindings : undefined
                                            }
                                        });
                                    }
                                }
                            })
                        )
                    )
                );
            };
        }
    );
})();

