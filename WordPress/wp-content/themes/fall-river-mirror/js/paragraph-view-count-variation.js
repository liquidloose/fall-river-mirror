/**
 * Paragraph Block Variation Bound to Article View Count
 *
 * This file registers a custom variation for the core/paragraph block that is
 * pre-configured with a block binding to the _article_view_count meta field.
 *
 * When a user inserts this variation, the paragraph will automatically display
 * the _article_view_count value for the current article post. The binding uses
 * the 'fr-mirror/article-meta' source with the key '_article_view_count'.
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

        registerBlockVariation('core/paragraph', {
            name: 'article-view-count',
            title: __('Article View Count', 'fall-river-mirror'),
            description: __('Displays the article view count from meta field.', 'fall-river-mirror'),
            keywords: ['view count', 'article', 'count', 'meta'],
            scope: ['inserter', 'block'],
            isDefault: false,
            attributes: {
                content: '',
                metadata: {
                    bindings: {
                        content: {
                            source: 'fr-mirror/article-meta',
                            args: {
                                key: '_article_view_count',
                            },
                        },
                    },
                },
            },
        });
    }

    tryRegister();
})();
