<?php
/**
 * Article Custom Post Type
 * 
 * This file handles everything related to the Article post type:
 * - Post type registration
 * - Meta boxes for selecting Journalists
 * - REST API registration for block editor compatibility
 * 
 * @package FallRiverMirror
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

// ============================================================================
// POST TYPE REGISTRATION
// ============================================================================

/**
 * Register Article Custom Post Type
 * 
 * Articles are the main content type for news stories. They support:
 * - Title, editor (content), author, featured image, excerpt, comments
 * - Public URLs (accessible on frontend)
 * - Archive pages (lists all articles)
 * - Gutenberg block editor (show_in_rest = true)
 * 
 * URL structure: /article/article-slug/
 * 
 * @hook init - Runs when WordPress initializes
 * @return void
 */
if (!function_exists('register_article_post_type')) {
function register_article_post_type() {
    register_post_type('article', array(
        'labels' => array(
            'name' => 'Articles',
            'singular_name' => 'Article',
            'add_new' => 'Add New Article',
            'add_new_item' => 'Add New Article',
            'edit_item' => 'Edit Article',
            'view_item' => 'View Article',
            'search_items' => 'Search Articles',
            'not_found' => 'No articles found',
            'not_found_in_trash' => 'No articles found in trash',
            'menu_name' => 'Articles',
        ),
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-media-document',
        'menu_position' => 5,
        'supports' => array('title', 'editor', 'author', 'thumbnail', 'excerpt', 'comments', 'custom-fields'),
        'rewrite' => array('slug' => 'article'), // URL slug for permalinks
        'show_in_rest' => true, // Enable Gutenberg block editor
        'show_ui' => true, // Show in admin interface
        'show_in_menu' => true, // Show in admin menu
        'show_in_admin_bar' => true, // Show "New Article" in admin bar
    ));
}
}
add_action('init', 'register_article_post_type');

// ============================================================================
// TAXONOMY REGISTRATION
// ============================================================================

/**
 * Register Categories for Article Post Type
 * 
 * This associates the built-in 'category' taxonomy with the Article post type
 * so that categories can be used to organize Articles. This also makes the
 * taxonomy filter available in Query blocks for Article post types.
 * 
 * @hook init - Runs when WordPress initializes
 * @return void
 */
if (!function_exists('register_article_taxonomies')) {
    function register_article_taxonomies() {
        // Register category taxonomy for Article post type
        register_taxonomy_for_object_type('category', 'article');
        
        // Ensure categories are available in REST API for Query blocks
        // Get the category taxonomy object
        $category = get_taxonomy('category');
        if ($category) {
            // Make sure it's enabled for REST API
            $category->show_in_rest = true;
        }
    }
    }
    add_action('init', 'register_article_taxonomies', 20); // Priority 20 ensures post type is registered first

    /**
 * Sort Articles by Meeting Date in Category Archives
 * 
 * This modifies category archive queries to sort by meeting_date meta field
 * instead of the default post_date.
 * 
 * @hook pre_get_posts
 * @param WP_Query $query The WP_Query object
 * @return void
 */
if (!function_exists('sort_category_archives_by_meeting_date')) {
    function sort_category_archives_by_meeting_date($query) {
        // Only run on frontend category archive pages
        if (is_admin() || !$query->is_main_query()) {
            return;
        }
        
        // Check if we're on a category archive page and querying articles
        if (is_category() && $query->get('post_type') === 'article' || 
            (is_array($query->get('post_type')) && in_array('article', $query->get('post_type')))) {
            
            // Sort by meeting_date meta field
            $query->set('meta_key', '_article_meeting_date');
            $query->set('orderby', 'meta_value'); // Use 'meta_value_num' if dates are stored as timestamps
            $query->set('order', 'DESC'); // or 'ASC' for oldest first
            
            // Optional: Only show posts that have a meeting_date
            // $query->set('meta_compare', 'EXISTS');
        }
    }
    }
    add_action('pre_get_posts', 'sort_category_archives_by_meeting_date', 10);

/**
 * Modify Query Block Query Vars to Sort by Meeting Date
 * 
 * This specifically targets Query blocks and modifies their query
 * to sort Articles by meeting_date meta field in category archives.
 * 
 * @hook query_loop_block_query_vars
 * @param array $query Array of query variables.
 * @param WP_Block $block Block instance.
 * @return array Modified query variables
 */
if (!function_exists('sort_query_block_by_meeting_date')) {
function sort_query_block_by_meeting_date($query, $block) {
    // Only modify queries for Article post type
    $post_type = $query['post_type'] ?? '';
    
    if ($post_type === 'article' || (is_array($post_type) && in_array('article', $post_type))) {
        // Check if we're on a category archive page
        if (is_category()) {
            // Override orderby to sort by _article_meeting_date meta field
            $query['meta_key'] = '_article_meeting_date';
            $query['meta_query'] = array(
                array( 'key' => '_article_meeting_date', 'compare' => 'EXISTS' ),
            );
            $query['orderby'] = 'meta_value';
            $query['order'] = 'DESC';
        }
    }
    
    return $query;
}
}
add_filter('query_loop_block_query_vars', 'sort_query_block_by_meeting_date', 10, 2);

// ============================================================================
// REST API REGISTRATION
// ============================================================================

/**
 * Register Article Meta Fields for REST API / Block Editor
 * 
 * This registers the 'journalists' meta field with WordPress's REST API.
 * This is required for:
 * 1. Gutenberg Block Editor - makes field available in the editor
 * 2. REST API Access - allows field to be read/written via API endpoints
 * 3. JavaScript Access - enables custom blocks/plugins to access the data
 * 
 * @hook init - Runs when WordPress initializes (before REST API is set up)
 * @return void
 */
if (!function_exists('get_article_custom_fields')) {
function get_article_custom_fields() {
    return array(
        '_article_content' => array(
            'label' => 'Content',
            'type' => 'string',
            'sanitize' => 'wp_kses_post',
        ),
        '_article_committee' => array(
            'label' => 'Committee',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        '_article_youtube_id' => array(
            'label' => 'YouTube ID',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        '_article_bullet_points' => array(
            'label' => 'Bullet Points',
            'type' => 'string',
            'sanitize' => 'sanitize_textarea_field',
        ),
        '_article_meeting_date' => array(
            'label' => 'Meeting Date',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        '_article_view_count' => array(
            'label' => 'View Count',
            'type' => 'integer',
            'sanitize' => 'absint',
        ),
    );
}
}

if (!function_exists('register_article_meta_fields')) {
function register_article_meta_fields() {
    /**
     * Register Article Journalists Meta Field
     * 
     * This field stores an array of Journalist post IDs associated with an Article.
     * Special handling required for array type.
     */
    register_post_meta('article', '_article_journalists', array(
        'show_in_rest' => array(
            'schema' => array(
                'type'  => 'array',        // The field is an array
                'items' => array(
                    'type' => 'number',    // Each item is a number (post ID)
                ),
                'default' => array(),
            ),
        ),
        'single' => true,                   // Store as single meta value
        'type' => 'array',                  // PHP type: array
        'auth_callback' => function() {     // Permission check
            return current_user_can('edit_posts'); 
        },
        'get_callback' => function($object, $field_name, $request, $object_type) {
            // $object can be WP_Post object or array with 'id' key depending on context
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return array();
            }
            // Retrieve the value from database
            $journalists = get_post_meta($post_id, '_article_journalists', true);
            // Handle serialized arrays (WordPress may serialize arrays in post meta)
            if (is_string($journalists) && !empty($journalists)) {
                $unserialized = maybe_unserialize($journalists);
                if (is_array($unserialized)) {
                    $journalists = $unserialized;
                }
            }
            // Ensure it's always an array
            return is_array($journalists) ? $journalists : array();
        },
        'update_callback' => function($value, $object, $field_name, $request, $object_type) {
            // $object can be WP_Post object or array with 'id' key depending on context
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
            }
            // Ensure value is an array
            $journalists = is_array($value) ? $value : array();
            // Sanitize each ID to ensure they're integers
            $sanitized_journalists = array_map('absint', $journalists);
            // Remove duplicates
            $sanitized_journalists = array_unique($sanitized_journalists);
            // Save to database
            $result = update_post_meta($post_id, '_article_journalists', $sanitized_journalists);
            // Return true on success, WP_Error on failure
            if ($result === false) {
                return new WP_Error('update_failed', 'Failed to update journalists field', array('status' => 500));
            }
            return true;
        }
    ));

    /**
     * Register Article Artists Meta Field
     * 
     * This field stores an array of Artist post IDs associated with an Article.
     * Special handling required for array type.
     */
    register_post_meta('article', '_article_artists', array(
        'show_in_rest' => array(
            'schema' => array(
                'type'  => 'array',        // The field is an array
                'items' => array(
                    'type' => 'number',    // Each item is a number (post ID)
                ),
                'default' => array(),
            ),
        ),
        'single' => true,                   // Store as single meta value
        'type' => 'array',                  // PHP type: array
        'auth_callback' => function() {     // Permission check
            return current_user_can('edit_posts'); 
        },
        'get_callback' => function($object, $field_name, $request, $object_type) {
            // $object can be WP_Post object or array with 'id' key depending on context
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return array();
            }
            // Retrieve the value from database
            $artists = get_post_meta($post_id, '_article_artists', true);
            // Handle serialized arrays (WordPress may serialize arrays in post meta)
            if (is_string($artists) && !empty($artists)) {
                $unserialized = maybe_unserialize($artists);
                if (is_array($unserialized)) {
                    $artists = $unserialized;
                }
            }
            // Ensure it's always an array
            return is_array($artists) ? $artists : array();
        },
        'update_callback' => function($value, $object, $field_name, $request, $object_type) {
            // $object can be WP_Post object or array with 'id' key depending on context
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
            }
            // Ensure value is an array
            $artists = is_array($value) ? $value : array();
            // Sanitize each ID to ensure they're integers
            $sanitized_artists = array_map('absint', $artists);
            // Remove duplicates
            $sanitized_artists = array_unique($sanitized_artists);
            // Save to database
            $result = update_post_meta($post_id, '_article_artists', $sanitized_artists);
            // Return true on success, WP_Error on failure
            if ($result === false) {
                return new WP_Error('update_failed', 'Failed to update artists field', array('status' => 500));
            }
            return true;
        }
    ));

    /**
     * Register Article Custom Fields
     * 
     * Loop through all fields defined in the configuration and register
     * each one with the REST API.
     */
    $article_custom_fields = get_article_custom_fields();
    foreach (array_keys($article_custom_fields) as $field_key) {
        $field_config = $article_custom_fields[$field_key];
        $meta_key = $field_key;
        $sanitize_function = $field_config['sanitize'];
        $field_type = $field_config['type'];
        
        // Determine schema default based on type
        $schema_default = ($field_type === 'integer') ? 0 : '';
        
        register_post_meta('article', $meta_key, array(
            'show_in_rest' => array(
                'schema' => array(
                    'type' => $field_type,
                    'default' => $schema_default,
                ),
            ),
            'single' => true,
            'type' => $field_type,
            'auth_callback' => function() {
                return current_user_can('edit_posts'); 
            },
            'get_callback' => function($object, $field_name, $request, $object_type) use ($meta_key, $field_type) {
                if (is_array($object) && isset($object['id'])) {
                    $post_id = $object['id'];
                } elseif (is_object($object) && isset($object->ID)) {
                    $post_id = $object->ID;
                } else {
                    return ($field_type === 'integer') ? 0 : '';
                }
                $value = get_post_meta($post_id, $meta_key, true);
                // For integer fields, ensure we return an integer
                if ($field_type === 'integer') {
                    return $value !== '' && $value !== false ? intval($value) : 0;
                }
                return $value;
            },
            'update_callback' => function($value, $object, $field_name, $request, $object_type) use ($meta_key, $sanitize_function, $field_type) {
                if (is_array($object) && isset($object['id'])) {
                    $post_id = $object['id'];
                } elseif (is_object($object) && isset($object->ID)) {
                    $post_id = $object->ID;
                } else {
                    return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
                }
                
                // Handle null/empty values
                if ($field_type === 'integer') {
                    $raw_value = ($value === null || $value === false) ? 0 : $value;
                } else {
                    $raw_value = ($value === null || $value === false) ? '' : $value;
                }
                
                // Sanitize the value using the field's sanitization function
                $sanitized_value = call_user_func($sanitize_function, $raw_value);
                
                // Save to database
                $result = update_post_meta($post_id, $meta_key, $sanitized_value);
                
                // Return true on success, WP_Error on failure
                if ($result === false) {
                    return new WP_Error('update_failed', 'Failed to update meta field', array('status' => 500));
                }
                return true;
            }
        ));
    }
}
}
add_action('init', 'register_article_meta_fields');

// ============================================================================
// ADMIN COLUMNS
// ============================================================================

/**
 * Add Meeting Date column to Articles admin list
 * 
 * @hook manage_article_posts_columns
 * @param array $columns Existing columns
 * @return array Modified columns array
 */
if (!function_exists('add_article_meeting_date_column')) {
function add_article_meeting_date_column($columns) {
    // Insert Meeting Date column after Title
    $new_columns = array();
    foreach ($columns as $key => $value) {
        $new_columns[$key] = $value;
        if ($key === 'title') {
            $new_columns['meeting_date'] = 'Meeting Date';
        }
    }
    // If title column wasn't found, just append it
    if (!isset($new_columns['meeting_date'])) {
        $new_columns['meeting_date'] = 'Meeting Date';
    }
    return $new_columns;
}
}
add_filter('manage_article_posts_columns', 'add_article_meeting_date_column');

/**
 * Display Meeting Date column content
 * 
 * @hook manage_article_posts_custom_column
 * @param string $column Column name
 * @param int $post_id Post ID
 * @return void
 */
if (!function_exists('display_article_meeting_date_column')) {
function display_article_meeting_date_column($column, $post_id) {
    if ($column === 'meeting_date') {
        $meeting_date = get_post_meta($post_id, '_article_meeting_date', true);
        if (!empty($meeting_date)) {
            // Format the date nicely (assuming it's stored as YYYY-MM-DD)
            $date_obj = DateTime::createFromFormat('Y-m-d', $meeting_date);
            if ($date_obj) {
                echo esc_html($date_obj->format('M j, Y')); // e.g., "Nov 26, 2025"
            } else {
                // If not in expected format, display as-is
                echo esc_html($meeting_date);
            }
        } else {
            echo '<span style="color: #999;">—</span>';
        }
    }
}
}
add_action('manage_article_posts_custom_column', 'display_article_meeting_date_column', 10, 2);

/**
 * Make Meeting Date column sortable
 * 
 * @hook manage_edit-article_sortable_columns
 * @param array $columns Existing sortable columns
 * @return array Modified sortable columns array
 */
if (!function_exists('make_article_meeting_date_sortable')) {
function make_article_meeting_date_sortable($columns) {
    $columns['meeting_date'] = 'meeting_date';
    return $columns;
}
}
add_filter('manage_edit-article_sortable_columns', 'make_article_meeting_date_sortable');

/**
 * Handle sorting by Meeting Date
 * 
 * @hook pre_get_posts
 * @param WP_Query $query The WP_Query object
 * @return void
 */
if (!function_exists('sort_articles_by_meeting_date')) {
function sort_articles_by_meeting_date($query) {
    // Only run in admin and for article post type
    if (!is_admin() || !$query->is_main_query()) {
        return;
    }
  
    
    // Check if sorting by meeting_date
    $orderby = $query->get('orderby');
    if ($orderby === 'meeting_date') {
        $query->set('meta_key', '_article_meeting_date');
        $query->set('orderby', 'meta_value'); // Sort as string
        // For date sorting, you might want to use 'meta_value_num' if dates are numeric
        // But since dates are stored as YYYY-MM-DD strings, 'meta_value' works fine
    }
}
}
add_action('pre_get_posts', 'sort_articles_by_meeting_date');

