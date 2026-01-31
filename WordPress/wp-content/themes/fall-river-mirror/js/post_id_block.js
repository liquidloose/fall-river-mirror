(function () {
    const { useEffect, createElement: el } = wp.element;
    const { Dashicon } = wp.components;
    const { useSelect } = wp.data;
    const { addFilter } = wp.hooks;

    wp.blocks.registerBlockType('fr-mirror/post-id-block', {
        apiVersion: 3,
        title: 'Bullet Points Block',
        icon: el(Dashicon, { icon: 'star' }),
        category: 'common',
        attributes: {
            postId: { type: 'string' }, // To store the ID if needed
        },
        usesContext: ['postId', 'postType'], // Access post ID and type
        edit: function (props) {
            const { attributes, setAttributes, context } = props;
            const { postId: contextPostId, postType } = context || {}; // Get ID from context

            // Check if current post type is 'article' and get post ID
            const currentPostType = useSelect(function (select) {
                return select('core/editor').getCurrentPostType();
            }, []);

            // Also get post ID from editor store as fallback
            const editorPostId = useSelect(function (select) {
                return select('core/editor').getCurrentPostId();
            }, []);

            // Get bullet_points from post meta
            const meta = useSelect(function (select) {
                return select('core/editor').getEditedPostAttribute('meta');
            }, []);

            const bulletPoints = meta && meta._article_bullet_points ? meta._article_bullet_points : '';

            // Show message if not on article post type
            if (currentPostType !== 'article') {
                return el('div', { style: { padding: '10px', backgroundColor: '#fff3cd', border: '1px solid #ffc107' } },
                    el('p', { style: { margin: 0 } }, 'This block is only available for Article post types.')
                );
            }

            // Display bullet points preview in editor
            if (!bulletPoints) {
                return el('div', { style: { padding: '10px', border: '1px dashed #ccc' } },
                    el('p', { style: { margin: 0, fontStyle: 'italic', color: '#666' } }, 'No bullet points set for this article.')
                );
            }

            return el('div', {
                className: 'fr-mirror-bullet-points',
                dangerouslySetInnerHTML: { __html: bulletPoints }
            });
        },
        save: function () {
            // Return null to use PHP render_callback for frontend rendering
            // This allows us to get the actual post ID from context at render time
            return null;
        },
    });

    // Hide block from inserter for non-article post types
    // This filter runs when blocks are being filtered for the inserter
    addFilter(
        'blocks.getBlockType',
        'fr-mirror/post-id-block-restrict',
        function (settings, name) {
            if (name !== 'fr-mirror/post-id-block') {
                return settings;
            }

            // Check current post type
            const postType = wp.data.select('core/editor')?.getCurrentPostType();

            // Only show in inserter when post type is 'article', hide otherwise
            if (postType !== 'article') {
                return {
                    ...settings,
                    supports: {
                        ...(settings.supports || {}),
                        inserter: false
                    }
                };
            }

            return settings;
        }
    );
})();

