<?php
/**
 * Newspaper FSE Theme functions and definitions
 *
 * @link https://developer.wordpress.org/themes/basics/theme-functions/
 *
 * @package Newspaper_FSE
 * @since 1.0.0
 */
if (!defined('ABSPATH')) {
    exit;
}

// Include custom post types
require get_template_directory() . '/inc/custom-post-types.php';

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

