/**
 * Paragraph Block Variation Bound to Article Journalist Bio
 * 
 * This file registers a custom variation for the core/paragraph block that is
 * pre-configured with a block binding to display the short bio of the first
 * journalist associated with an article.
 * 
 * When a user inserts this variation, the paragraph will automatically display
 * the journalist's short bio for the current article.
 * The binding uses the 'fr-mirror/article-meta' source with the key
 * 'short_bio', which retrieves the bio_short from the first journalist.
 * 
 * This variation is useful in article templates and patterns where you want to
 * display the journalist's bio without manually configuring the binding each time.
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/block-editor/reference-guides/block-api/block-variations/
 * @see fr_mirror_get_article_meta_binding() for the binding callback
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
         * Register Paragraph Block Variation Bound to Journalist Bio
         * 
         * This registers a custom variation for the core/paragraph block that is
         * pre-configured with a block binding to display the journalist's short bio.
         * 
         * The 'metadata.bindings' structure configures the block binding:
         * - 'content' is the attribute being bound (the paragraph text)
         * - 'source' is 'fr-mirror/article-meta' (the registered article binding source)
         * - 'args.key' is 'short_bio' (key that retrieves bio_short from first journalist)
         */
        registerBlockVariation('core/paragraph', {
            name: 'article-journalist-bio',
            title: __('Article Journalist Bio', 'fall-river-mirror'),
            description: __('Displays the short bio of the first journalist associated with the article.', 'fall-river-mirror'),
            keywords: ['journalist', 'article', 'bio', 'biography', 'author', 'byline'],
            scope: ['inserter', 'block'],
            isDefault: false,
            attributes: {
                content: '', // Empty content - will be populated by binding
                metadata: {
                    bindings: {
                        content: {
                            source: 'fr-mirror/article-meta',
                            args: {
                                key: 'short_bio',
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

