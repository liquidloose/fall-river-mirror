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
// META BOXES
// ============================================================================
// 
// NOTE: Meta boxes have been removed in favor of the Gutenberg sidebar panel.
// All journalist selection is now handled via the block editor sidebar.
// The REST API registration below handles saving from Gutenberg.
//

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
        'article_content' => array(
            'label' => 'Content',
            'type' => 'string',
            'sanitize' => 'wp_kses_post',
        ),
        'committee' => array(
            'label' => 'Committee',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        'youtube_id' => array(
            'label' => 'YouTube ID',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        'bullet_points' => array(
            'label' => 'Bullet Points',
            'type' => 'string',
            'sanitize' => 'sanitize_textarea_field',
        ),
        'meeting_date' => array(
            'label' => 'Meeting Date',
            'type' => 'string',
            'sanitize' => 'sanitize_text_field',
        ),
        'view_count' => array(
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
     * Register Article Custom Fields
     * 
     * Loop through all fields defined in the configuration and register
     * each one with the REST API.
     */
    $article_custom_fields = get_article_custom_fields();
    foreach (array_keys($article_custom_fields) as $field_key) {
        $field_config = $article_custom_fields[$field_key];
        // Special handling: keep meta key as _article_content for article_content field
        $meta_key = ($field_key === 'article_content') 
            ? '_article_content' 
            : '_article_' . $field_key;
        $sanitize_function = $field_config['sanitize'];
        $field_type = $field_config['type'];
        
        // Skip registering 'article_content' field with show_in_rest to prevent auto UI generation
        // We'll handle it manually in the custom panel
        if ($field_key === 'article_content') {
            continue;
        }
        
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
    
    // Register content field separately for REST API (without auto UI generation)
    // We handle the UI manually in the custom panel
    register_post_meta('article', '_article_content', array(
        'show_in_rest' => array(
            'schema' => array(
                'type' => 'string',
                'default' => '',
            ),
        ),
        'single' => true,
        'type' => 'string',
        'auth_callback' => function() {
            return current_user_can('edit_posts'); 
        },
        'get_callback' => function($object, $field_name, $request, $object_type) {
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return '';
            }
            return get_post_meta($post_id, '_article_content', true);
        },
        'update_callback' => function($value, $object, $field_name, $request, $object_type) {
            if (is_array($object) && isset($object['id'])) {
                $post_id = $object['id'];
            } elseif (is_object($object) && isset($object->ID)) {
                $post_id = $object->ID;
            } else {
                return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
            }
            $sanitized_value = wp_kses_post($value);
            $result = update_post_meta($post_id, '_article_content', $sanitized_value);
            if ($result === false) {
                return new WP_Error('update_failed', 'Failed to update content field', array('status' => 500));
            }
            return true;
        }
    ));
}
}
add_action('init', 'register_article_meta_fields');

