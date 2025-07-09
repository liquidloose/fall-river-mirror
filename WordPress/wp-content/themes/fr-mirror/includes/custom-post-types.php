<?php
// Register Custom Post Types for Newspaper Theme
function newspaper_register_post_types() {
    
    // Register Article CPT
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
        ),
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-media-document',
        'menu_position' => 5,
        'supports' => array('title', 'editor', 'author', 'thumbnail', 'excerpt', 'comments'),
        'rewrite' => array('slug' => 'article'),
        'show_in_rest' => true, // Enable Gutenberg editor
    ));
    
    // Register Journalist CPT
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
        ),
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-admin-users',
        'menu_position' => 6,
        'supports' => array('title', 'editor', 'thumbnail'),
        'rewrite' => array('slug' => 'journalist'),
        'show_in_rest' => true, // Enable Gutenberg editor
    ));
}
add_action('init', 'newspaper_register_post_types');

// Add Journalists Meta Box to Articles
function add_journalists_meta_box() {
    add_meta_box(
        'journalists_meta_box',
        'Article Journalists',
        'render_journalists_meta_box',
        'article',
        'side',
        'default'
    );
}
add_action('add_meta_boxes', 'add_journalists_meta_box');

// Render Meta Box Content
function render_journalists_meta_box($post) {
    wp_nonce_field('save_journalists_data', 'journalists_meta_box_nonce');
    
    // Get saved journalists for this article
    $assigned_journalists = get_post_meta($post->ID, '_article_journalists', true);
    if (!is_array($assigned_journalists)) {
        $assigned_journalists = array();
    }
    
    // Get all journalists
    $journalists = get_posts(array(
        'post_type' => 'journalist',
        'posts_per_page' => -1,
        'orderby' => 'title',
        'order' => 'ASC',
    ));
    
    if (empty($journalists)) {
        echo '<p>No journalists found. <a href="' . admin_url('post-new.php?post_type=journalist') . '">Add a journalist</a>.</p>';
        return;
    }
    
    echo '<div style="max-height: 200px; overflow-y: auto;">';
    foreach ($journalists as $journalist) {
        $checked = in_array($journalist->ID, $assigned_journalists) ? 'checked="checked"' : '';
        echo '<label style="display: block; margin-bottom: 5px;">';
        echo '<input type="checkbox" name="article_journalists[]" value="' . $journalist->ID . '" ' . $checked . '> ';
        echo esc_html($journalist->post_title);
        echo '</label>';
    }
    echo '</div>';
}

// Save Meta Box Data
function save_journalists_meta_data($post_id) {
    // Check if our nonce is set and verify it
    if (!isset($_POST['journalists_meta_box_nonce']) || 
        !wp_verify_nonce($_POST['journalists_meta_box_nonce'], 'save_journalists_data')) {
        return;
    }
    
    // Check user permissions
    if (!current_user_can('edit_post', $post_id)) {
        return;
    }
    
    // Don't save during autosave
    if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
        return;
    }
    
    // Check if correct post type
    if ('article' !== get_post_type($post_id)) {
        return;
    }
    
    // Update the meta field
    if (isset($_POST['article_journalists'])) {
        $journalists = array_map('absint', $_POST['article_journalists']);
        update_post_meta($post_id, '_article_journalists', $journalists);
    } else {
        update_post_meta($post_id, '_article_journalists', array());
    }
}
add_action('save_post', 'save_journalists_meta_data');

/**
 * Register custom meta fields for the block editor
 */
function newspaper_register_meta_fields() {
    register_post_meta('article', 'journalists', array(
        'show_in_rest' => array(
            'schema' => array(
                'type'  => 'array',
                'items' => array(
                    'type' => 'number',
                ),
            ),
        ),
        'single' => true,
        'type' => 'array',
        'auth_callback' => function() { 
            return current_user_can('edit_posts'); 
        }
    ));
}
add_action('init', 'newspaper_register_meta_fields');