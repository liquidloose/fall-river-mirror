<?php
/**
 * Artist Custom Post Type
 * 
 * This file handles everything related to the Artist post type:
 * - Post type registration
 * - Custom fields configuration
 * - Meta boxes for custom fields
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
 * Register Artist Custom Post Type
 * 
 * Artists represent creative contributors. They support:
 * - Title (name), editor (bio), featured image
 * - Public URLs and archive pages
 * - Gutenberg block editor
 * - Custom meta fields (defined below)
 * 
 * URL structure: /artist/artist-slug/
 * 
 * @hook init - Runs when WordPress initializes
 * @return void
 */
if (!function_exists('register_artist_post_type')) {
function register_artist_post_type() {
    register_post_type('artist', array(
        'labels' => array(
            'name' => 'Artists',
            'singular_name' => 'Artist',
            'add_new' => 'Add New Artist',
            'add_new_item' => 'Add New Artist',
            'edit_item' => 'Edit Artist',
            'view_item' => 'View Artist',
            'search_items' => 'Search Artists',
            'not_found' => 'No artists found',
            'not_found_in_trash' => 'No artists found in trash',
            'menu_name' => 'Artists',
        ),
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-art',
        'menu_position' => 7,
        'supports' => array('title', 'editor', 'thumbnail', 'custom-fields'), // Enable custom fields support
        'rewrite' => array('slug' => 'artist'), // URL slug for permalinks
        'show_in_rest' => true, // Enable Gutenberg block editor
        'show_ui' => true, // Show in admin interface
        'show_in_menu' => true, // Show in admin menu
        'show_in_admin_bar' => true, // Show "New Artist" in admin bar
    ));
}
}
add_action('init', 'register_artist_post_type');

// ============================================================================
// CUSTOM FIELDS CONFIGURATION
// ============================================================================

/**
 * Get Artist Custom Fields Configuration
 * 
 * This function returns an array defining all custom fields for the Artist
 * post type. Each field is configured with:
 * 
 * Required properties:
 * - 'label': The field label shown in the WordPress admin
 * - 'type': HTML input type (text, email, url, textarea, etc.)
 * - 'sanitize': WordPress sanitization function name (e.g., 'sanitize_email')
 * 
 * Optional properties:
 * - 'description': Help text shown below the field
 * - 'placeholder': Placeholder text shown in empty fields
 * - 'rows': For textarea fields, number of rows (default: 3)
 * 
 * How it works:
 * This configuration array is used by:
 * 1. render_artist_fields_meta_box() - to generate the HTML form fields
 * 2. save_artist_fields_meta_data() - to know how to sanitize each field
 * 3. register_artist_meta_fields() - to register fields for REST API
 * 
 * To add a new field:
 * Simply add a new entry to the array below. The system will automatically:
 * - Create the form field in the admin
 * - Handle saving and sanitization
 * - Register it for the block editor
 * 
 * @return array Associative array of field configurations
 *               Format: 'field_key' => array('label' => ..., 'type' => ..., ...)
 */
if (!function_exists('get_artist_custom_fields')) {
function get_artist_custom_fields() {
    return array(
        // Note: 'name' field removed - using post title instead
        'first_name' => array(
            'label' => 'First Name',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => '',
        ),
        'last_name' => array(
            'label' => 'Last Name',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => '',
        ),
        'title' => array(
            'label' => 'Title/Position',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => 'e.g., Photographer, Illustrator, etc.',
        ),
        'email' => array(
            'label' => 'Email',
            'type' => 'email',
            'sanitize' => 'sanitize_email',
            'description' => '',
        ),
        'website' => array(
            'label' => 'Website',
            'type' => 'url',
            'sanitize' => 'esc_url_raw',
            'description' => 'Personal or portfolio website',
            'placeholder' => 'https://example.com',
        ),
        'instagram' => array(
            'label' => 'Instagram',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => '',
            'placeholder' => '@username',
        ),
        'bio_short' => array(
            'label' => 'Short Bio',
            'type' => 'textarea',
            'sanitize' => 'sanitize_textarea_field',
            'description' => 'A brief bio or description of the artist.',
            'rows' => 3,
        ),
    );
}
}

// ============================================================================
// META BOXES
// ============================================================================
// 
// NOTE: Meta boxes have been removed in favor of the Gutenberg sidebar panel.
// All meta field editing is now handled via the block editor sidebar.
// The REST API registration below handles saving from Gutenberg.
//

// ============================================================================
// REST API REGISTRATION
// ============================================================================

/**
 * Register Artist Meta Fields for REST API / Block Editor
 * 
 * This registers all custom fields with WordPress's REST API.
 * This is required for:
 * 1. Gutenberg Block Editor - makes fields available in the editor
 * 2. REST API Access - allows fields to be read/written via API endpoints
 * 3. JavaScript Access - enables custom blocks/plugins to access the data
 * 
 * @hook init - Runs when WordPress initializes (before REST API is set up)
 * @return void
 */
if (!function_exists('register_artist_meta_fields')) {
function register_artist_meta_fields() {
    /**
     * Register Artist Custom Fields
     * 
     * Loop through all fields defined in the configuration and register
     * each one with the REST API. This makes them available in:
     * - Gutenberg block editor
     * - REST API endpoints
     * - JavaScript/React components
     * 
     * Each field is registered with:
     * - Meta key: '_artist_' + field_key (e.g., '_artist_email')
     * - Type: 'string' (all our fields are strings)
     * - Single value: true (one value per field)
     * - REST API: enabled (show_in_rest = true)
     */
    $artist_custom_fields = get_artist_custom_fields();
    foreach (array_keys($artist_custom_fields) as $field_key) {
        $field_config = $artist_custom_fields[$field_key];
        $meta_key = '_artist_' . $field_key;
        $sanitize_function = $field_config['sanitize'];
        
        register_post_meta('artist', $meta_key, array(
            'show_in_rest' => array(
                'schema' => array(
                    'type' => 'string',
                    'default' => '',
                ),
            ),
            'single' => true,                  // Store as single meta value
            'type' => 'string',              // PHP type: string
            'auth_callback' => function() {  // Permission check
                return current_user_can('edit_posts'); 
            },
            'get_callback' => function($object, $field_name, $request, $object_type) use ($meta_key) {
                // $object can be WP_Post object or array with 'id' key depending on context
                if (is_array($object) && isset($object['id'])) {
                    $post_id = $object['id'];
                } elseif (is_object($object) && isset($object->ID)) {
                    $post_id = $object->ID;
                } else {
                    return '';
                }
                // Retrieve the value from database
                return get_post_meta($post_id, $meta_key, true);
            },
            'update_callback' => function($value, $object, $field_name, $request, $object_type) use ($meta_key, $sanitize_function) {
                // $object can be WP_Post object or array with 'id' key depending on context
                if (is_array($object) && isset($object['id'])) {
                    $post_id = $object['id'];
                } elseif (is_object($object) && isset($object->ID)) {
                    $post_id = $object->ID;
                } else {
                    return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
                }
                // Handle null/empty values - convert to empty string for consistency
                $raw_value = ($value === null || $value === false) ? '' : $value;
                // Sanitize the value using the field's sanitization function
                $sanitized_value = call_user_func($sanitize_function, $raw_value);
                // Save to database - update_post_meta returns meta_id (new) or true (updated) or false (error)
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
add_action('init', 'register_artist_meta_fields');

