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

// Include block bindings
require_once get_template_directory() . '/includes/block-bindings.php';

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

