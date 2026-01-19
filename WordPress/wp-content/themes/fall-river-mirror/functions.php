<?php

if(!ABSPATH) {
    exit; // Exit if accessed directly
}

// Include custom post types
require_once get_template_directory() . '/includes/article-api-endpoint.php';
require_once get_template_directory() . '/includes/custom-post-types.php';
require_once get_template_directory() . '/includes/article-content-template.php';

// Include block styles
require_once get_template_directory() . '/includes/block-styles.php';

// Include query loop variations
require_once get_template_directory() . '/includes/query_loop_filtered_by_meeting_date.php';

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
        'paragraph-meeting-date-variation',
        get_template_directory_uri() . '/js/paragraph-meeting-date-variation.js',
        array(
            'wp-blocks',
            'wp-i18n'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'paragraph-journalist-variation',
        get_template_directory_uri() . '/js/paragraph-journalist-variation.js',
        array(
            'wp-blocks',
            'wp-i18n'
        ),
        wp_get_theme()->get('Version'),
        true
    );
    
    wp_enqueue_script(
        'paragraph-artist-variation',
        get_template_directory_uri() . '/js/paragraph-artist-variation.js',
        array(
            'wp-blocks',
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
    
    wp_enqueue_script(
        'fr-mirror-post-id-block',
        get_template_directory_uri() . '/js/post_id_block.js',
        array(
            'wp-blocks',
            'wp-element',
            'wp-block-editor',
            'wp-components',
            'wp-data',
            'wp-hooks'
        ),
        wp_get_theme()->get('Version'),
        true
    );
}
add_action( 'enqueue_block_editor_assets', 'fall_river_mirror_enqueue_block_editor_assets' );

/**
 * Register Post ID Block with PHP render callback
 * 
 * This allows the block to get the actual post ID from context at render time,
 * which is especially important when the block is used in templates.
 */
function fr_mirror_register_post_id_block() {
    register_block_type('fr-mirror/post-id-block', array(
        'render_callback' => 'fr_mirror_render_post_id_block',
        'uses_context' => array('postId', 'postType'),
    ));
}
add_action('init', 'fr_mirror_register_post_id_block');

/**
 * Render callback for Post ID Block
 * 
 * Gets the bullet_points meta field from the post and displays it.
 * 
 * @param array    $attributes Block attributes
 * @param string   $content    Block content (not used)
 * @param WP_Block $block      Block instance with context
 * @return string HTML output
 */
function fr_mirror_render_post_id_block($attributes, $content, $block) {
    // Get post ID from block context (available when template is rendered)
    $post_id = $block->context['postId'] ?? get_the_ID();
    
    // Validate it's a numeric ID
    $post_id = is_numeric($post_id) ? (int) $post_id : null;
    
    if (!$post_id) {
        return '<div class="fr-mirror-bullet-points-block"></div>';
    }
    
    // Get bullet_points meta field
    $bullet_points = get_post_meta($post_id, '_article_bullet_points', true);
    
    if (empty($bullet_points)) {
        return '<div class="fr-mirror-bullet-points-block"></div>';
    }
    
    // Output bullet points with proper sanitization (same as shortcode)
    return '<div class="fr-mirror-bullet-points">' . wp_kses_post($bullet_points) . '</div>';
}

/**
 * Enqueue frontend scripts
 */
function fall_river_mirror_enqueue_frontend_assets() {
	wp_enqueue_script(
		'fr-mirror-bullet-points-processor',
		get_template_directory_uri() . '/js/bullet-points-processor.js',
		array(),
		wp_get_theme()->get('Version'),
		true
	);
}
add_action( 'wp_enqueue_scripts', 'fall_river_mirror_enqueue_frontend_assets' );

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

    if ( $field_key === 'bullet_points' ) {
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

/**
 * Include Article Post Type in Category Archive Queries
 * 
 * This modifies category archive queries to include Articles.
 * Without this, category archives only show regular 'post' post types.
 * 
 * @hook pre_get_posts
 * @param WP_Query $query The WP_Query object
 * @return void
 */
if (!function_exists('include_articles_in_category_archives')) {
    function include_articles_in_category_archives($query) {
        // Only run on frontend category archive pages
        if (is_admin() || !$query->is_main_query()) {
            return;
        }
        
        // Check if we're on a category archive page
        if (is_category()) {
            // Set post type to include Articles
            $query->set('post_type', array('post', 'article'));
        }
    }
    }
    add_action('pre_get_posts', 'include_articles_in_category_archives');

