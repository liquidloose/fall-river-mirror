<?php
/**
 * Custom Post Types Loader
 * 
 * This file serves as the entry point for all custom post types.
 * It includes separate files for each post type to keep the codebase
 * organized and maintainable.
 * 
 * File structure:
 * - article-post-type.php - Article post type, meta boxes, and REST API
 * - journalist-post-type.php - Journalist post type, custom fields, meta boxes, and REST API
 * - artist-post-type.php - Artist post type, custom fields, meta boxes, and REST API
 * 
 * @package FallRiverMirror
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

// Include Article post type
require_once get_template_directory() . '/includes/article-post-type.php';

// Include Journalist post type
require_once get_template_directory() . '/includes/journalist-post-type.php';

// Include Artist post type
require_once get_template_directory() . '/includes/artist-post-type.php';