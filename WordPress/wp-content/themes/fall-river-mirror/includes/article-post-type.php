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
if (!function_exists('register_article_meta_fields')) {
function register_article_meta_fields() {
    /**
     * Register Article Journalists Meta Field
     * 
     * This field stores an array of Journalist post IDs associated with an Article.
     * 
     * Schema breakdown:
     * - 'type' => 'array': The field contains an array
     * - 'items' => array('type' => 'number'): Each item in the array is a number (post ID)
     * - 'single' => true: Store as a single meta value (not multiple values per key)
     * - 'show_in_rest': Makes it available in REST API and block editor
     * - 'auth_callback': Only users who can edit posts can access this field
     */
    // Register the meta field with proper callbacks
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
}
}
add_action('init', 'register_article_meta_fields');

