<?php

/**
 * Generate the required blocks with bindings for article post_content
 * 
 * @param string $title Optional. The post title to include in the heading block. If not provided, uses empty heading.
 * @return string The block-formatted content with bindings
 */
function fr_mirror_get_required_article_blocks( $title = '' ) {
    // Escape the title for use in HTML
    $title_html = $title ? esc_html( $title ) : '';
    
    return "<!-- wp:heading -->
<h2 class=\"wp-block-heading\">{$title_html}</h2>
<!-- /wp:heading -->

<!-- wp:paragraph {\"metadata\":{\"bindings\":{\"content\":{\"source\":\"fr-mirror/article-meta\",\"args\":{\"key\":\"_article_bullet_points\"}}}}} -->
<p></p>
<!-- /wp:paragraph -->

<!-- wp:paragraph {\"metadata\":{\"bindings\":{\"content\":{\"source\":\"fr-mirror/article-meta\",\"args\":{\"key\":\"_article_content\"}}}}} -->
<p></p>
<!-- /wp:paragraph -->

<!-- wp:paragraph {\"metadata\":{\"bindings\":{\"content\":{\"source\":\"fr-mirror/article-meta\",\"args\":{\"key\":\"_article_content\"}}}}} -->
<p></p>
<!-- /wp:paragraph -->";
}


/**
 * Fix existing articles to ensure they have required blocks
 * Run this once via WP-CLI: wp eval "fr_mirror_fix_existing_article_blocks();"
 * Or call it from a temporary admin page/endpoint
 * 
 * @return int Number of posts fixed
 */
function fr_mirror_fix_existing_article_blocks() {
    $articles = get_posts( array(
        'post_type' => 'article',
        'posts_per_page' => -1,
        'post_status' => 'any',
    ) );
    
    $fixed = 0;
    foreach ( $articles as $article ) {
        $current_content = $article->post_content;
        
        // Check if required blocks are missing (heading block or article-meta bindings)
        $has_heading_block = strpos( $current_content, 'wp:heading' ) !== false;
        $has_article_meta = strpos( $current_content, 'fr-mirror/article-meta' ) !== false;
        
        // Update if content is empty or missing any required blocks
        if ( empty( $current_content ) || ! $has_heading_block || ! $has_article_meta ) {
            
            wp_update_post( array(
                'ID' => $article->ID,
                'post_content' => fr_mirror_get_required_article_blocks( $article->post_title ),
            ) );
            
            $fixed++;
        }
    }
    
    return $fixed;
}

// Temporary endpoint to fix existing articles - REMOVE AFTER USE
add_action( 'rest_api_init', function() {
    register_rest_route( 'fr-mirror/v2', '/fix-article-blocks', array(
        'methods' => 'POST',
        'callback' => function() {
            $fixed = fr_mirror_fix_existing_article_blocks();
            return new WP_REST_Response( array(
                'message' => "Fixed $fixed articles",
                'fixed_count' => $fixed
            ), 200 );
        },
        'permission_callback' => '__return_true',
    ) );
} );

// TEMPORARY: Fix existing articles - REMOVE AFTER RUNNING
add_action( 'admin_init', function() {
    // Only run once - check if option exists
    if ( ! get_option( 'fr_mirror_blocks_with_title_fixed' ) ) {
        $fixed = fr_mirror_fix_existing_article_blocks();
        update_option( 'fr_mirror_blocks_with_title_fixed', true );
        error_log( "Fixed $fixed article posts with required blocks including title" );
    }
} );