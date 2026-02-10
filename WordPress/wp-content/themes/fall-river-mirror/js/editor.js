/**
 * Register Block Bindings Source in JavaScript
 * 
 * This registers the block binding source on the JavaScript side
 * to make bindings work in the editor.
 */

(function() {
    // Wait for wp.blocks to be available
    function tryRegister() {
        if (typeof wp === 'undefined' || typeof wp.blocks === 'undefined') {
            setTimeout(tryRegister, 100);
            return;
        }
        
        // Check if registerBlockBindingsSource exists
        if (typeof wp.blocks.registerBlockBindingsSource !== 'function') {
            return;
        }
        
        // Define which article meta fields are available for binding
        const articleEditableAttributes = [
            '_article_content',
            '_article_committee',
            '_article_youtube_id',
            '_article_bullet_points',
            '_article_meeting_date',
            '_article_view_count'
        ];
        
        const articleReadOnlyAttributes = [
            '_article_content',
            '_article_committee',
            '_article_youtube_id',
            '_article_bullet_points',
            '_article_meeting_date',
            '_article_view_count'
        ];
        
        // Define which journalist meta fields are available for binding
        const journalistEditableAttributes = [
            'first_name',
            'last_name',
            'email',
            'phone',
            'title',
            'twitter',
            'linkedin',
            'bio_short'
        ];
        
        const journalistReadOnlyAttributes = [
            'first_name',
            'last_name',
            'email',
            'phone',
            'title',
            'twitter',
            'linkedin',
            'bio_short'
        ];
        
        // Define which artist meta fields are available for binding
        const artistEditableAttributes = [
            'first_name',
            'last_name',
            'title',
            'email',
            'website',
            'instagram',
            'bio_short'
        ];
        
        const artistReadOnlyAttributes = [
            'first_name',
            'last_name',
            'title',
            'email',
            'website',
            'instagram',
            'bio_short'
        ];
        
        // Register article meta block bindings source
        wp.blocks.registerBlockBindingsSource({
            name: 'fr-mirror/article-meta',
            usesContext: [ 'postId', 'postType' ],
            getValues( { select, bindings } ) {
                const values = {};
                const meta = select( 'core/editor' ).getEditedPostAttribute( 'meta' );
                
                if ( ! meta ) {
                    return values;
                }
                
                for ( const [ attributeName, source ] of Object.entries( bindings ) ) {
                    if ( source.args && source.args.key ) {
                        const fieldKey = source.args.key;
                        
                        // Only return values for fields that are in our allowed lists
                        if (
                            articleEditableAttributes.includes( fieldKey )
                            || articleReadOnlyAttributes.includes( fieldKey )
                        ) {
                            const metaKey = fieldKey;
                            
                            // Get the value from meta object
                            const value = meta[ metaKey ];
                            if ( value !== undefined ) {
                                values[ attributeName ] = value;
                            }
                        }
                    }
                }
                
                return values;
            },
        });
        
        // Register journalist meta block bindings source
        wp.blocks.registerBlockBindingsSource({
            name: 'fr-mirror/journalist-meta',
            usesContext: [ 'postId', 'postType' ],
            getValues( { select, bindings } ) {
                const values = {};
                const meta = select( 'core/editor' ).getEditedPostAttribute( 'meta' );
                
                if ( ! meta ) {
                    return values;
                }
                
                for ( const [ attributeName, source ] of Object.entries( bindings ) ) {
                    if ( source.args && source.args.key ) {
                        const fieldKey = source.args.key;
                        
                        // Only return values for fields that are in our allowed lists
                        if (
                            journalistEditableAttributes.includes( fieldKey )
                            || journalistReadOnlyAttributes.includes( fieldKey )
                        ) {
                            // Construct meta key: '_journalist_' + field_key
                            const metaKey = '_journalist_' + fieldKey;
                            
                            // Get the value from meta object
                            const value = meta[ metaKey ];
                            if ( value !== undefined ) {
                                values[ attributeName ] = value;
                            }
                        }
                    }
                }
                
                return values;
            },
        });
        
        // Register artist meta block bindings source
        wp.blocks.registerBlockBindingsSource({
            name: 'fr-mirror/artist-meta',
            usesContext: [ 'postId', 'postType' ],
            getValues( { select, bindings } ) {
                const values = {};
                const meta = select( 'core/editor' ).getEditedPostAttribute( 'meta' );
                
                if ( ! meta ) {
                    return values;
                }
                
                for ( const [ attributeName, source ] of Object.entries( bindings ) ) {
                    if ( source.args && source.args.key ) {
                        const fieldKey = source.args.key;
                        
                        // Only return values for fields that are in our allowed lists
                        if (
                            artistEditableAttributes.includes( fieldKey )
                            || artistReadOnlyAttributes.includes( fieldKey )
                        ) {
                            // Construct meta key: '_artist_' + field_key
                            const metaKey = '_artist_' + fieldKey;
                            
                            // Get the value from meta object
                            const value = meta[ metaKey ];
                            if ( value !== undefined ) {
                                values[ attributeName ] = value;
                            }
                        }
                    }
                }
                
                return values;
            },
        });
    }
    
    // Start trying to register
    tryRegister();
})();

