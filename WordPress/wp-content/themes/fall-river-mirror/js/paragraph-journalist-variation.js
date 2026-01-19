/**
 * Paragraph Block Variation Bound to Article Journalist Full Name
 * 
 * This file registers a custom variation for the core/paragraph block that is
 * pre-configured with a block binding to display the full name of the first
 * journalist associated with an article.
 * 
 * When a user inserts this variation, the paragraph will automatically display
 * the journalist's full name (first_name + last_name) for the current article.
 * The binding uses the 'fr-mirror/article-meta' source with the key
 * 'journalist_full_name', which is handled specially in the PHP callback to
 * combine first_name and last_name from the first journalist.
 * 
 * This variation is useful in article templates and patterns where you want to
 * display the journalist's name without manually configuring the binding each time.
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/block-editor/reference-guides/block-api/block-variations/
 * @see fr_mirror_get_article_meta_binding() for the binding callback that combines names
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
         * Register Paragraph Block Variation Bound to Journalist Full Name
         * 
         * This registers a custom variation for the core/paragraph block that is
         * pre-configured with a block binding to display the journalist's full name.
         * 
         * The 'metadata.bindings' structure configures the block binding:
         * - 'content' is the attribute being bound (the paragraph text)
         * - 'source' is 'fr-mirror/article-meta' (the registered article binding source)
         * - 'args.key' is 'journalist_full_name' (special key that combines first_name + last_name)
         * 
         * The PHP callback (fr_mirror_get_article_meta_binding) handles the special
         * 'journalist_full_name' key by:
         * 1. Getting the article's _article_journalists (array of journalist IDs)
         * 2. Getting the first journalist's first_name and last_name
         * 3. Combining them with a space
         */
        registerBlockVariation('core/paragraph', {
            name: 'article-journalist-full-name',
            title: __('Article Journalist Full Name', 'fall-river-mirror'),
            description: __('Displays the full name of the first journalist associated with the article.', 'fall-river-mirror'),
            keywords: ['journalist', 'article', 'name', 'author', 'byline'],
            scope: ['inserter', 'block'],
            isDefault: false,
            attributes: {
                content: '', // Empty content - will be populated by binding
                metadata: {
                    bindings: {
                        content: {
                            source: 'fr-mirror/article-meta',
                            args: {
                                key: 'journalist_full_name',
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

