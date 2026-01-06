<?php

if(!ABSPATH) {
    exit; // Exit if accessed directly
}

// Include custom post types
require_once get_template_directory() . '/includes/article-api-endpoint.php';
require_once get_template_directory() . '/includes/custom-post-types.php';
require_once get_template_directory() . '/includes/article-content-template.php';


/**
 * Register custom block styles and enqueue block stylesheets
 */
function my_theme_register_block_styles() {
    // Register the custom group style
    register_block_style(
        'core/group',
        array(
            'name'  => 'rivedge-box-shadow',
            'label' => __( 'Rivedge Box Shadow', 'my-theme' ),
            'isDefault' => false, 
        )
    );

    // Register the custom navigation
    register_block_style(
        'core/navigation',
        array(
            'name'  => 'rivedge-navigation',
            'label' => __('Rivedge Box Shadow', 'my-theme'),
            'isDefault' => false,
        )
    );


    // Enqueue the group block stylesheet
    wp_enqueue_block_style(
        'core/group',
        array(
            'handle' => 'rivedge-theme-group-style',
            'src'    => get_theme_file_uri('assets/css/blocks/core-group.css'),
            'path'   => get_theme_file_path('assets/css/blocks/core-group.css'),
            'deps'   => array(),
            'ver'    => wp_get_theme()->get('Version'),
        )
    );

    // Enqueue the group block stylesheet
    wp_enqueue_block_style(
        'core/group',
        array(
            'handle' => 'rivedge-theme-group-style',
            'src'    => get_theme_file_uri( 'assets/css/blocks/core-group.css' ),
            'path'   => get_theme_file_path( 'assets/css/blocks/core-group.css' ),
            'deps'   => array(),
            'ver'    => wp_get_theme()->get( 'Version' ),
        )
    );

    // Enqueue the group block stylesheet
    wp_enqueue_block_style(
        'core/navigation',
        array(
            'handle' => 'rivedge-theme-navigation-style',
            'src'    => get_theme_file_uri('assets/css/blocks/core-navigation.css'),
            'path'   => get_theme_file_path('assets/css/blocks/core-navigation.css'),
            'deps'   => array(),
            'ver'    => wp_get_theme()->get('Version'),
        )
    );
}
add_action( 'init', 'my_theme_register_block_styles' );

/**
 * Enqueue Gutenberg editor scripts for custom meta panels
 * 
 * This loads the JavaScript file that adds custom meta field panels
 * to the Document sidebar in the Gutenberg block editor.
 * The JavaScript file itself checks the post type and only shows on journalist posts.
 */
function fall_river_mirror_enqueue_block_editor_assets() {
    wp_enqueue_script(
        'journalist-meta-panel',
        get_template_directory_uri() . '/js/journalist-meta-panel.js',
        array(
            'wp-plugins',
            'wp-editor',
            'wp-element',
            'wp-components',
            'wp-data',
            'wp-core-data',
            'wp-i18n',
            'wp-api-fetch'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'artist-meta-panel',
        get_template_directory_uri() . '/js/artist-meta-panel.js',
        array(
            'wp-plugins',
            'wp-editor',
            'wp-element',
            'wp-components',
            'wp-data',
            'wp-core-data',
            'wp-i18n',
            'wp-api-fetch'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'article-meta-panel',
        get_template_directory_uri() . '/js/article-meta-panel.js',
        array(
            'wp-plugins',
            'wp-editor',
            'wp-element',
            'wp-components',
            'wp-data',
            'wp-core-data',
            'wp-i18n',
            'wp-api-fetch'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'article-meta-block-bindings',
        get_template_directory_uri() . '/js/article-meta-block-bindings.js',
        array(
            'wp-blocks',
            'wp-element',
            'wp-data',
            'wp-block-editor',
            'wp-api-fetch',
            'wp-core-data',
            'wp-components',
            'wp-compose',
            'wp-hooks',
            'wp-i18n'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'journalist-meta-block-bindings',
        get_template_directory_uri() . '/js/journalist-meta-block-bindings.js',
        array(
            'wp-blocks',
            'wp-element',
            'wp-data',
            'wp-block-editor',
            'wp-api-fetch',
            'wp-core-data',
            'wp-components',
            'wp-compose',
            'wp-hooks',
            'wp-i18n'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'artist-meta-block-bindings',
        get_template_directory_uri() . '/js/artist-meta-block-bindings.js',
        array(
            'wp-blocks',
            'wp-element',
            'wp-data',
            'wp-block-editor',
            'wp-api-fetch',
            'wp-core-data',
            'wp-components',
            'wp-compose',
            'wp-hooks',
            'wp-i18n'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'fr-mirror-editor',
        get_template_directory_uri() . '/js/editor.js',
        array(
            'wp-blocks',
            'wp-element',
            'wp-data',
            'wp-block-editor'
        ),
        wp_get_theme()->get('Version'),
        true
    );
}
add_action( 'enqueue_block_editor_assets', 'fall_river_mirror_enqueue_block_editor_assets' );

/**
 * Register Block Bindings for Article meta fields
 * 
 * This registers a block binding source that allows binding article meta fields
 * to block attributes in templates and patterns. This enables flexible layout
 * editing in the Gutenberg editor without requiring code changes.
 * 
 * Supported meta fields:
 * - content (HTML content)
 * - committee (string)
 * - youtube_id (string)
 * - bullet_points (text)
 * - meeting_date (string)
 * - view_count (integer)
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
 * The field key is specified in the binding args, and the meta key is constructed
 * as '_article_{key}'.
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
    
    // Special handling: keep meta key as _article_content for article_content field
    $meta_key = ($field_key === 'article_content') 
        ? '_article_content' 
        : '_article_' . $field_key;
    
    // Retrieve the meta value
    $value = get_post_meta( $post_id, $meta_key, true );
    
    // Debug: Log what we're retrieving
    if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
        error_log( sprintf( 'Block Binding: Post ID %d, Meta Key: %s, Value: %s', $post_id, $meta_key, substr( $value, 0, 100 ) ) );
    }
    
    // Handle empty values appropriately
    if ( $value === false || $value === '' ) {
        // For integer fields, return 0; for string fields, return empty string
          // Cast integer fields to string
    if ( $field_key === 'view_count' ) {
        return (string) $value;
    }
        return '';
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


