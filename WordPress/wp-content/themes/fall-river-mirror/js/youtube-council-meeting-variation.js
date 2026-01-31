/**
 * YouTube Embed Block Variation - Council Meeting
 * 
 * This file registers a custom variation for the core/embed block that automatically
 * populates the YouTube embed URL with the video ID from the article's _article_youtube_id
 * meta field. The URL is inserted into the block attributes before saving.
 * 
 * When a user inserts the "Council Meeting" variation:
 * 1. The variation is registered with YouTube provider settings
 * 2. JavaScript detects when the block is inserted/selected
 * 3. Fetches the YouTube video ID from article meta
 * 4. Constructs the YouTube URL and updates the block's url attribute
 * 5. Listens for meta changes to update URL if video ID changes
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/block-editor/reference-guides/block-api/block-variations/
 */

(function () {
    // Wait for WordPress blocks and data to be available
    function tryRegister() {
        if (typeof wp === 'undefined' || !wp.blocks || !wp.blocks.registerBlockVariation) {
            setTimeout(tryRegister, 100);
            return;
        }

        if (!wp.data || !wp.data.select || !wp.data.dispatch) {
            setTimeout(tryRegister, 100);
            return;
        }

        const { registerBlockVariation } = wp.blocks;
        const { __ } = wp.i18n;
        const { addFilter } = wp.hooks;
        const { select, dispatch } = wp.data;

        /**
         * Register YouTube Embed Block Variation - Council Meeting
         * 
         * This variation appears in the block inserter as "Council Meeting"
         * and is pre-configured for YouTube embeds.
         */
        registerBlockVariation('core/embed', {
            name: 'council-meeting',
            title: __('Council Meeting', 'fall-river-mirror'),
            description: __('Embeds YouTube video from article YouTube ID.', 'fall-river-mirror'),
            keywords: ['youtube', 'council', 'meeting', 'video', 'embed'],
            scope: ['inserter', 'block'],
            isDefault: false,
            attributes: {
                providerNameSlug: 'youtube',
                __frmCouncilMeeting: true, // Custom identifier for this variation
            },
        });

        /**
         * Update embed block URL with YouTube video ID from article meta
         * 
         * @param {string} clientId - The block's client ID
         */
        function updateEmbedUrlFromMeta(clientId) {
            // Get the block
            const block = select('core/block-editor').getBlock(clientId);

            // Check if this is our Council Meeting variation
            if (!block || block.name !== 'core/embed') {
                return;
            }

            const isCouncilMeeting = block.attributes.__frmCouncilMeeting === true ||
                (block.attributes.providerNameSlug === 'youtube' &&
                    block.attributes.__frmCouncilMeeting !== false);

            if (!isCouncilMeeting) {
                return;
            }

            // Get current post meta
            const meta = select('core/editor').getEditedPostAttribute('meta');
            const youtubeId = meta && meta._article_youtube_id ? meta._article_youtube_id : '';

            // If we have a video ID and the URL hasn't been set yet (or needs updating)
            if (youtubeId) {
                const youtubeUrl = `https://www.youtube.com/watch?v=${youtubeId}`;

                // Only update if URL is different or empty
                if (!block.attributes.url || block.attributes.url !== youtubeUrl) {
                    dispatch('core/block-editor').updateBlockAttributes(clientId, {
                        url: youtubeUrl,
                    });
                }
            } else {
                // No video ID - show placeholder message
                // The embed block will show its default "Enter URL" state
                // We could optionally set a placeholder URL or message here
            }
        }

        /**
         * Filter block editor to add custom behavior when Council Meeting variation is inserted
         * Using editor.BlockEdit filter (same pattern as other meta binding files)
         */
        addFilter(
            'editor.BlockEdit',
            'fr-mirror/council-meeting-embed',
            function (BlockEdit) {
                return function (props) {
                    const { name, attributes, setAttributes, clientId } = props;
                    const { useEffect } = wp.element;
                    const { useSelect } = wp.data;

                    // Log all embed blocks to see what we're getting
                    if (name === 'core/embed') {
                        console.log('Embed block detected:', {
                            name: name,
                            clientId: clientId,
                            attributes: attributes,
                            __frmCouncilMeeting: attributes.__frmCouncilMeeting,
                            providerNameSlug: attributes.providerNameSlug
                        });
                    }

                    // Only process embed blocks
                    if (name !== 'core/embed') {
                        return wp.element.createElement(BlockEdit, props);
                    }

                    // Check if this is a Council Meeting variation
                    // Also check if it's YouTube with no URL (might be our variation)
                    const isCouncilMeeting = attributes.__frmCouncilMeeting === true ||
                        (attributes.providerNameSlug === 'youtube' && !attributes.url);

                    // Get meta using useSelect hook - this automatically subscribes to changes
                    const meta = useSelect(function (select) {
                        return select('core/editor').getEditedPostAttribute('meta');
                    }, []);

                    // Extract YouTube ID from meta
                    const youtubeId = meta && meta._article_youtube_id ? meta._article_youtube_id : '';

                    // Update URL when block is mounted or when YouTube ID changes
                    useEffect(function () {
                        console.log('Embed useEffect running:', {
                            isCouncilMeeting: isCouncilMeeting,
                            youtubeId: youtubeId,
                            hasMeta: !!meta,
                            currentUrl: attributes.url
                        });

                        if (!isCouncilMeeting) {
                            console.log('Not a Council Meeting variation, skipping');
                            return;
                        }

                        // Debug logging
                        console.log('Council Meeting Embed - Processing:', {
                            clientId: clientId,
                            isCouncilMeeting: isCouncilMeeting,
                            youtubeId: youtubeId,
                            currentUrl: attributes.url,
                            meta: meta,
                            attributes: attributes
                        });

                        // Update URL if we have a video ID and it's different from current URL
                        if (youtubeId) {
                            const youtubeUrl = `https://www.youtube.com/watch?v=${youtubeId}`;

                            // Only update if URL is different or empty
                            if (!attributes.url || attributes.url !== youtubeUrl) {
                                console.log('Updating embed URL to:', youtubeUrl);
                                setAttributes({
                                    url: youtubeUrl,
                                });
                            } else {
                                console.log('URL already set correctly');
                            }
                        } else {
                            console.log('No YouTube ID found in meta. Meta object:', meta);
                        }
                    }, [clientId, isCouncilMeeting, youtubeId]);

                    // Render the original block edit component
                    return wp.element.createElement(BlockEdit, props);
                };
            }
        );

        /**
         * Hook into block insertion to update URL immediately when variation is inserted
         */
        addFilter(
            'blocks.insertBlock',
            'fr-mirror/council-meeting-embed-insert',
            function (block, index, rootClientId) {
                // Check if this is our Council Meeting variation
                if (block && block.name === 'core/embed' && block.attributes && block.attributes.__frmCouncilMeeting === true) {
                    // Get meta to find YouTube ID
                    const meta = select('core/editor').getEditedPostAttribute('meta');
                    const youtubeId = meta && meta._article_youtube_id ? meta._article_youtube_id : '';

                    if (youtubeId) {
                        const youtubeUrl = `https://www.youtube.com/watch?v=${youtubeId}`;

                        // Update the block attributes with the URL
                        // Use setTimeout to ensure block is fully registered
                        setTimeout(function () {
                            const blocks = select('core/block-editor').getBlocks();
                            blocks.forEach(function (insertedBlock) {
                                if (insertedBlock.name === 'core/embed' &&
                                    insertedBlock.attributes.__frmCouncilMeeting === true &&
                                    (!insertedBlock.attributes.url || insertedBlock.attributes.url !== youtubeUrl)) {
                                    dispatch('core/block-editor').updateBlockAttributes(insertedBlock.clientId, {
                                        url: youtubeUrl,
                                    });
                                }
                            });
                        }, 100);
                    }
                }

                return block;
            }
        );

    }

    // Start trying to register
    tryRegister();
})();

