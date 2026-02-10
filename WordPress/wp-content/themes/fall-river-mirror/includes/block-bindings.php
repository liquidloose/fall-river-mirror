<?php
/**
 * Block Bindings
 * 
 * This file handles all block binding registrations and callbacks for the theme.
 * Block bindings allow blocks to dynamically display content from post meta fields
 * and other sources in templates and patterns.
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

/**
 * Register Block Bindings for Article meta fields
 * 
 * This registers a block binding source that allows binding article meta fields
 * to block attributes in templates and patterns. This enables flexible layout
 * editing in the Gutenberg editor without requiring code changes.
 * 
 * Supported meta fields:
 * - _article_content (HTML content)
 * - _article_committee (string)
 * - _article_youtube_id (string)
 * - _article_bullet_points (text)
 * - _article_meeting_date (string)
 * - _article_view_count (integer)
 * 
 * @return void
 */
function fr_mirror_register_article_meta_bindings() {
    // Check if block bindings are supported (WordPress 6.5+)
    if ( ! function_exists( 'register_block_bindings_source' ) ) {
        return;
    }
    
    register_block_bindings_source(
        'fr-mirror/article-meta',
        array(
            'label'              => __( 'Article Meta', 'fr-mirror' ),
            'get_value_callback' => 'fr_mirror_get_article_meta_binding',
            'uses_context'       => array( 'postId', 'postType' )
        )
    );
}
add_action( 'init', 'fr_mirror_register_article_meta_bindings' );

/**
 * Get value for article meta block binding
 * 
 * Callback function that retrieves article meta field values for block bindings.
 * The field key is specified in the binding args and used directly as the meta key.
 * 
 * @param array     $source_args    Arguments passed from the block binding, including 'key' parameter.
 * @param WP_Block  $block_instance The block instance containing context information.
 * @param string    $attribute_name The name of the block attribute being bound.
 * @return mixed|null The meta field value, or null if post ID is unavailable.
 */
function fr_mirror_get_article_meta_binding( array $source_args, WP_Block $block_instance, string $attribute_name ) {
    // Get post ID from block context or fall back to current post
    $post_id = $block_instance->context['postId'] ?? get_the_ID();
    
    // Debug: Log if we can't find post ID
    if ( ! $post_id && defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( 'Block Binding: No post ID found. Context: ' . print_r( $block_instance->context, true ) );
    }
    
    if ( ! $post_id ) {
        return null;
    }
    
    // Get the meta key from source args (e.g., 'article_content', 'committee', etc.)
    $field_key = $source_args['key'] ?? '';
    
    if ( empty( $field_key ) ) {
        return null;
    }
    
    // Special handling: journalist_full_name combines first_name and last_name from first journalist
    if ( $field_key === 'journalist_full_name' ) {
        // Get the article's journalist IDs
        $journalist_ids = get_post_meta( $post_id, '_article_journalists', true );
        
        if ( empty( $journalist_ids ) || ! is_array( $journalist_ids ) ) {
            return '';
        }
        
        // Get the first journalist ID
        $first_journalist_id = $journalist_ids[0];
        
        if ( ! $first_journalist_id ) {
            return '';
        }
        
        // Get first and last name from the journalist post
        $first_name = get_post_meta( $first_journalist_id, '_journalist_first_name', true );
        $last_name = get_post_meta( $first_journalist_id, '_journalist_last_name', true );
        
        // Combine them with a space
        $full_name = trim( $first_name . ' ' . $last_name );
        
        if ( empty( $full_name ) ) {
            return '';
        }
        
        // Create a URL-friendly slug from the full name
        // Convert to lowercase, replace spaces with hyphens, remove special characters
        $name_slug = sanitize_title( $full_name );
        
        // Build the URL dynamically using the journalist's name
        // The full name is interpolated into the URL path - no hardcoded prefix
        $journalist_url = home_url( sprintf( '/%s/', $name_slug ) );
        
        // Return the name wrapped in an anchor tag
        return sprintf(
            '<a href="%s">%s</a>',
            esc_url( $journalist_url ),
            esc_html( $full_name )
        );
    }
    
    // Special handling: artist_full_name combines first_name and last_name from first artist
    if ( $field_key === 'artist_full_name' ) {
        // Get the article's artist IDs
        $artist_ids = get_post_meta( $post_id, '_article_artists', true );
        
        if ( empty( $artist_ids ) || ! is_array( $artist_ids ) ) {
            return '';
        }
        
        // Get the first artist ID
        $first_artist_id = $artist_ids[0];
        
        if ( ! $first_artist_id ) {
            return '';
        }
        
        // Get first and last name from the artist post
        $first_name = get_post_meta( $first_artist_id, '_artist_first_name', true );
        $last_name = get_post_meta( $first_artist_id, '_artist_last_name', true );
        
        // Combine them with a space
        $full_name = trim( $first_name . ' ' . $last_name );
        
        if ( empty( $full_name ) ) {
            return '';
        }
        
        // Get the artist post to get its slug
        $artist_post = get_post( $first_artist_id );
        if ( ! $artist_post ) {
            return esc_html( $full_name );
        }
        
        // Build the artist URL using the post slug
        // URL structure: /artist/{slug}/
        $artist_slug = $artist_post->post_name;
        $artist_url = home_url( sprintf( '/artist/%s/', $artist_slug ) );
        
        // Return the name wrapped in an anchor tag
        return sprintf(
            '<a href="%s">%s</a>',
            esc_url( $artist_url ),
            esc_html( $full_name )
        );
    }
    
    $meta_key = $field_key;
    
    // Retrieve the meta value
    $value = get_post_meta( $post_id, $meta_key, true );
    
    // Debug: Log what we're retrieving
    if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( sprintf( 'Block Binding: Post ID %d, Meta Key: %s, Value: %s', $post_id, $meta_key, substr( $value, 0, 100 ) ) );
    }
    
    // Handle empty values appropriately
    if ( $value === false || $value === '' ) {
        // For integer fields like _article_view_count, return '0' when empty
        if ( $field_key === '_article_view_count' ) {
            return (string) ( $value ?: 0 );
        }
        return '';
    }

    if ( $field_key === '_article_bullet_points' ) {
        return wp_kses( $value, array(
            'ul' => array( 'class' => array(), 'id' => array() ),
            'li' => array( 'class' => array() ),
            'strong' => array(),
            'em' => array(),
        ) );
    }
    
    return $value;
}

/**
 * Register Block Bindings for Journalist meta fields
 * 
 * This registers a block binding source that allows binding journalist meta fields
 * to block attributes in templates and patterns. This enables flexible layout
 * editing in the Gutenberg editor without requiring code changes.
 * 
 * Supported meta fields:
 * - first_name (string)
 * - last_name (string)
 * - email (string)
 * - phone (string)
 * - title (string)
 * - twitter (string)
 * - linkedin (string)
 * - bio_short (string)
 * 
 * @return void
 */
function fr_mirror_register_journalist_meta_bindings() {
    // Check if block bindings are supported (WordPress 6.5+)
    if ( ! function_exists( 'register_block_bindings_source' ) ) {
        return;
    }
    
    register_block_bindings_source(
        'fr-mirror/journalist-meta',
        array(
            'label'              => __( 'Journalist Meta', 'fr-mirror' ),
            'get_value_callback' => 'fr_mirror_get_journalist_meta_binding',
            'uses_context'       => array( 'postId', 'postType' )
        )
    );
}
add_action( 'init', 'fr_mirror_register_journalist_meta_bindings' );

/**
 * Get value for journalist meta block binding
 * 
 * Callback function that retrieves journalist meta field values for block bindings.
 * The field key is specified in the binding args, and the meta key is constructed
 * as '_journalist_{key}'.
 * 
 * @param array     $source_args    Arguments passed from the block binding, including 'key' parameter.
 * @param WP_Block  $block_instance The block instance containing context information.
 * @param string    $attribute_name The name of the block attribute being bound.
 * @return mixed|null The meta field value, or null if post ID is unavailable.
 */
function fr_mirror_get_journalist_meta_binding( array $source_args, WP_Block $block_instance, string $attribute_name ) {
    // Get post ID from block context or fall back to current post
    $post_id = $block_instance->context['postId'] ?? get_the_ID();
    
    // Debug: Log if we can't find post ID
    if ( ! $post_id && defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( 'Block Binding: No post ID found. Context: ' . print_r( $block_instance->context, true ) );
    }
    
    if ( ! $post_id ) {
        return null;
    }
    
    // Get the meta key from source args (e.g., 'first_name', 'last_name', etc.)
    $field_key = $source_args['key'] ?? '';
    
    if ( empty( $field_key ) ) {
        return null;
    }
    
    // Construct meta key: '_journalist_' + field_key
    $meta_key = '_journalist_' . $field_key;
    
    // Retrieve the meta value
    $value = get_post_meta( $post_id, $meta_key, true );
    
    // Debug: Log what we're retrieving
    if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( sprintf( 'Block Binding: Post ID %d, Meta Key: %s, Value: %s', $post_id, $meta_key, substr( $value, 0, 100 ) ) );
    }
    
    // Handle empty values appropriately
    if ( $value === false || $value === '' ) {
        return '';
    }
    
    return $value;
}

/**
 * Register Block Bindings for Artist meta fields
 * 
 * This registers a block binding source that allows binding artist meta fields
 * to block attributes in templates and patterns. This enables flexible layout
 * editing in the Gutenberg editor without requiring code changes.
 * 
 * Supported meta fields:
 * - email (string)
 * - website (string)
 * - instagram (string)
 * - bio_short (string)
 * 
 * @return void
 */
function fr_mirror_register_artist_meta_bindings() {
    // Check if block bindings are supported (WordPress 6.5+)
    if ( ! function_exists( 'register_block_bindings_source' ) ) {
        return;
    }
    
    register_block_bindings_source(
        'fr-mirror/artist-meta',
        array(
            'label'              => __( 'Artist Meta', 'fr-mirror' ),
            'get_value_callback' => 'fr_mirror_get_artist_meta_binding',
            'uses_context'       => array( 'postId', 'postType' )
        )
    );
}
add_action( 'init', 'fr_mirror_register_artist_meta_bindings' );

/**
 * Get value for artist meta block binding
 * 
 * Callback function that retrieves artist meta field values for block bindings.
 * The field key is specified in the binding args, and the meta key is constructed
 * as '_artist_{key}'.
 * 
 * @param array     $source_args    Arguments passed from the block binding, including 'key' parameter.
 * @param WP_Block  $block_instance The block instance containing context information.
 * @param string    $attribute_name The name of the block attribute being bound.
 * @return mixed|null The meta field value, or null if post ID is unavailable.
 */
function fr_mirror_get_artist_meta_binding( array $source_args, WP_Block $block_instance, string $attribute_name ) {
    // Get post ID from block context or fall back to current post
    $post_id = $block_instance->context['postId'] ?? get_the_ID();
    
    // Debug: Log if we can't find post ID
    if ( ! $post_id && defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( 'Block Binding: No post ID found. Context: ' . print_r( $block_instance->context, true ) );
    }
    
    if ( ! $post_id ) {
        return null;
    }
    
    // Get the meta key from source args (e.g., 'email', 'website', etc.)
    $field_key = $source_args['key'] ?? '';
    
    if ( empty( $field_key ) ) {
        return null;
    }
    
    // Construct meta key: '_artist_' + field_key
    $meta_key = '_artist_' . $field_key;
    
    // Retrieve the meta value
    $value = get_post_meta( $post_id, $meta_key, true );
    
    // Debug: Log what we're retrieving
    if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( sprintf( 'Block Binding: Post ID %d, Meta Key: %s, Value: %s', $post_id, $meta_key, substr( $value, 0, 100 ) ) );
    }
    
    // Handle empty values appropriately
    if ( $value === false || $value === '' ) {
        return '';
    }
    
    return $value;
}

