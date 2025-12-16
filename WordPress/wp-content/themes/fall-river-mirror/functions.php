<?php

if(!ABSPATH) {
    exit; // Exit if accessed directly
}

include_once 'includes/article-api-endpoint.php';

// Include custom post types
require get_template_directory() . '/includes/custom-post-types.php';

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
}
add_action( 'enqueue_block_editor_assets', 'fall_river_mirror_enqueue_block_editor_assets' );

