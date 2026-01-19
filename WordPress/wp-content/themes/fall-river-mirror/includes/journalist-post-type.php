<?php
/**
 * Journalist Custom Post Type
 * 
 * This file handles everything related to the Journalist post type:
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
 * Register Journalist Custom Post Type
 * 
 * Journalists represent staff members/writers. They support:
 * - Title (name), editor (bio), featured image
 * - Public URLs and archive pages
 * - Gutenberg block editor
 * - Custom meta fields (defined below)
 * 
 * URL structure: /journalist/journalist-slug/
 * 
 * @hook init - Runs when WordPress initializes
 * @return void
 */
if (!function_exists('register_journalist_post_type')) {
function register_journalist_post_type() {
    register_post_type('journalist', array(
        'labels' => array(
            'name' => 'Journalists',
            'singular_name' => 'Journalist',
            'add_new' => 'Add New Journalist',
            'add_new_item' => 'Add New Journalist',
            'edit_item' => 'Edit Journalist',
            'view_item' => 'View Journalist',
            'search_items' => 'Search Journalists',
            'not_found' => 'No journalists found',
            'not_found_in_trash' => 'No journalists found in trash',
            'menu_name' => 'Journalists',
        ),
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-admin-users',
        'menu_position' => 6,
        'supports' => array('title', 'editor', 'thumbnail', 'custom-fields'), // Enable custom fields support
        'rewrite' => array('slug' => 'journalist'), // URL slug for permalinks
        'show_in_rest' => true, // Enable Gutenberg block editor
        'show_ui' => true, // Show in admin interface
        'show_in_menu' => true, // Show in admin menu
        'show_in_admin_bar' => true, // Show "New Journalist" in admin bar
    ));
}
}
add_action('init', 'register_journalist_post_type');

// ============================================================================
// CUSTOM FIELDS CONFIGURATION
// ============================================================================

/**
 * Get Journalist Custom Fields Configuration
 * 
 * This function returns an array defining all custom fields for the Journalist
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
 * 1. render_journalist_fields_meta_box() - to generate the HTML form fields
 * 2. save_journalist_fields_meta_data() - to know how to sanitize each field
 * 3. register_journalist_meta_fields() - to register fields for REST API
 * 
 * To add a new field:
 * Simply add a new entry to the array below. The system will automatically:
 * - Create the form field in the admin
 * - Handle saving and sanitization
 * - Register it for the block editor
 * 
 * Example:
 * 'website' => array(
 *     'label' => 'Website',
 *     'type' => 'url',
 *     'sanitize' => 'esc_url_raw',
 *     'description' => 'Personal or professional website',
 *     'placeholder' => 'https://example.com',
 * ),
 * 
 * @return array Associative array of field configurations
 *               Format: 'field_key' => array('label' => ..., 'type' => ..., ...)
 */
if (!function_exists('get_journalist_custom_fields')) {
function get_journalist_custom_fields() {
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
        'email' => array(
            'label' => 'Email',
            'type' => 'email',
            'sanitize' => 'sanitize_email',
            'description' => '',
        ),
        'phone' => array(
            'label' => 'Phone',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => '',
        ),
        'title' => array(
            'label' => 'Title/Position',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => 'e.g., Senior Reporter, Editor, etc.',
        ),
        'twitter' => array(
            'label' => 'Twitter/X',
            'type' => 'text',
            'sanitize' => 'sanitize_text_field',
            'description' => '',
            'placeholder' => '@username',
        ),
        'linkedin' => array(
            'label' => 'LinkedIn',
            'type' => 'url',
            'sanitize' => 'esc_url_raw',
            'description' => '',
            'placeholder' => 'https://linkedin.com/in/...',
        ),
        'bio_short' => array(
            'label' => 'Short Bio',
            'type' => 'textarea',
            'sanitize' => 'sanitize_textarea_field',
            'description' => 'A brief bio or tagline for the journalist.',
            'rows' => 3,
        ),
    );
}
}

// ============================================================================
// REST API REGISTRATION
// ============================================================================

/**
 * Register Journalist Meta Fields for REST API / Block Editor
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
if (!function_exists('register_journalist_meta_fields')) {
function register_journalist_meta_fields() {
    /**
     * Register Journalist Custom Fields
     * 
     * Loop through all fields defined in the configuration and register
     * each one with the REST API. This makes them available in:
     * - Gutenberg block editor
     * - REST API endpoints
     * - JavaScript/React components
     * 
     * Each field is registered with:
     * - Meta key: '_journalist_' + field_key (e.g., '_journalist_email')
     * - Type: 'string' (all our fields are strings)
     * - Single value: true (one value per field)
     * - REST API: enabled (show_in_rest = true)
     */
    $journalist_custom_fields = get_journalist_custom_fields();
    foreach (array_keys($journalist_custom_fields) as $field_key) {
        $field_config = $journalist_custom_fields[$field_key];
        $meta_key = '_journalist_' . $field_key;
        $sanitize_function = $field_config['sanitize'];
        
        register_post_meta('journalist', $meta_key, array(
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
                // Debug logging (commented out)
                // error_log('update_callback called for: ' . $meta_key . ' with value: ' . print_r($value, true));
                
                // $object can be WP_Post object or array with 'id' key depending on context
                if (is_array($object) && isset($object['id'])) {
                    $post_id = $object['id'];
                } elseif (is_object($object) && isset($object->ID)) {
                    $post_id = $object->ID;
                } else {
                    // error_log('Invalid object in update_callback: ' . print_r($object, true));
                    return new WP_Error('invalid_object', 'Invalid post object', array('status' => 400));
                }
                
                // error_log('Post ID: ' . $post_id);
                
                // Handle null/empty values - convert to empty string for consistency
                $raw_value = ($value === null || $value === false) ? '' : $value;
                // error_log('Raw value: ' . $raw_value);
                
                // Sanitize the value using the field's sanitization function
                $sanitized_value = call_user_func($sanitize_function, $raw_value);
                // error_log('Sanitized value: ' . $sanitized_value);
                
                // Save to database - update_post_meta returns meta_id (new) or true (updated) or false (error)
                $result = update_post_meta($post_id, $meta_key, $sanitized_value);
                // error_log('update_post_meta result: ' . print_r($result, true));
                
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
add_action('init', 'register_journalist_meta_fields');

