/**
 * Paragraph Block Variation Bound to Article Meeting Date
 * 
 * This file registers a custom variation for the core/paragraph block that is
 * pre-configured with a block binding to the article meeting_date meta field.
 * 
 * When a user inserts this variation, the paragraph will automatically display
 * the meeting_date value for the current article post. The binding uses the
 * 'fr-mirror/article-meta' source with the key 'meeting_date', which maps to
 * the '_article_meeting_date' meta key in the database.
 * 
 * This variation is useful in article templates and patterns where you want to
 * display the meeting date without manually configuring the binding each time.
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/block-editor/reference-guides/block-api/block-variations/
 */

(function () {
    // Wait for wp.blocks to be available
    function tryRegister() {
        if (typeof wp === 'undefined' || !wp.blocks || !wp.blocks.registerBlockVariation) {
            setTimeout(tryRegister, 100);
            return;
        }

        const { registerBlockVariation } = wp.blocks;
        const { __ } = wp.i18n;

        /**
         * Register Paragraph Block Variation Bound to Meeting Date
         * 
         * This registers a custom variation for the core/paragraph block that is
         * pre-configured with a block binding to the article meeting_date meta field.
         * 
         * The 'metadata.bindings' structure configures the block binding:
         * - 'content' is the attribute being bound (the paragraph text)
         * - 'source' is 'fr-mirror/article-meta' (the registered binding source)
         * - 'args.key' is 'meeting_date' (maps to '_article_meeting_date' meta key)
         */
        registerBlockVariation('core/paragraph', {
            name: 'article-meeting-date',
            title: __('Article Meeting Date', 'fall-river-mirror'),
            description: __('Displays the article meeting date from meta field.', 'fall-river-mirror'),
            keywords: ['meeting date', 'article', 'date', 'meta'],
            scope: ['inserter', 'block'],
            isDefault: false,
            attributes: {
                content: '', // Empty content - will be populated by binding
                metadata: {
                    bindings: {
                        content: {
                            source: 'fr-mirror/article-meta',
                            args: {
                                key: '_article_meeting_date',
                            },
                        },
                    },
                },
            },
        });
    }

    // Start trying to register
    tryRegister();
})();

