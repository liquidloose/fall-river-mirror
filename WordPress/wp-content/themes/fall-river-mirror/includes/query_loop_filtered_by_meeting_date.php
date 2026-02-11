<?php
/**
 * Query Loop Block Variation Filtered by Meeting Date
 * 
 * This file provides a custom Query Loop block variation for WordPress that filters
 * and sorts Article post types by the `_article_meeting_date` custom meta field.
 * 
 * The file handles three main responsibilities:
 * 1. Registers a custom block variation for the Query Loop block
 * 2. Filters query variables on the frontend to filter/sort by meeting_date
 * 3. Filters REST API queries in the editor to ensure consistent behavior
 * 
 * @package FallRiverMirror
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/block-editor/reference-guides/block-api/block-variations/
 * @see https://developer.wordpress.org/reference/hooks/query_loop_block_query_vars/
 * @see https://developer.wordpress.org/reference/hooks/rest_article_query/
 * 
 * Technical Details:
 * - Variation name: 'filtered-by-meeting-date'
 * - Meta key used: '_article_meeting_date'
 * - Default sort order: DESC (newest meeting dates first)
 * - Filter type: EXISTS (only shows articles with a meeting_date value)
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

/**
 * Add __frmCustomFieldFilter attribute to Query block so it is preserved when saving
 *
 * WordPress strips attributes that are not declared in the block's schema. Without
 * this, __frmCustomFieldFilter would be lost on save, causing our view-count and
 * meeting-date variations to fall back to default sorting.
 *
 * @hook register_block_type_args
 */
if ( ! function_exists( 'fall_river_mirror_add_query_block_custom_filter_attribute' ) ) {
    function fall_river_mirror_add_query_block_custom_filter_attribute( $args, $block_type ) {
        if ( 'core/query' !== $block_type ) {
            return $args;
        }
        $args['attributes']['__frmCustomFieldFilter'] = array(
            'type'    => 'string',
            'default' => '',
        );
        if ( ! isset( $args['providesContext'] ) ) {
            $args['providesContext'] = array();
        }
        $args['providesContext']['__frmCustomFieldFilter'] = '__frmCustomFieldFilter';
        return $args;
    }
}
add_filter( 'register_block_type_args', 'fall_river_mirror_add_query_block_custom_filter_attribute', 10, 2 );

/**
 * Add __frmCustomFieldFilter to Post Template's usesContext
 *
 * The Post Template receives context from its parent Query block. We need it to
 * consume __frmCustomFieldFilter so it's available when build_query_vars_from_query_block
 * runs. Without this, the attribute would not be in $block->context.
 */
if ( ! function_exists( 'fall_river_mirror_add_post_template_uses_context' ) ) {
    function fall_river_mirror_add_post_template_uses_context( $args, $block_type ) {
        if ( 'core/post-template' !== $block_type ) {
            return $args;
        }
        if ( ! isset( $args['usesContext'] ) || ! is_array( $args['usesContext'] ) ) {
            $args['usesContext'] = array();
        }
        if ( ! in_array( '__frmCustomFieldFilter', $args['usesContext'], true ) ) {
            $args['usesContext'][] = '__frmCustomFieldFilter';
        }
        return $args;
    }
}
add_filter( 'register_block_type_args', 'fall_river_mirror_add_post_template_uses_context', 10, 2 );

/**
 * Register Query Loop Block Variation Filtered by Meeting Date
 * 
 * Registers a custom variation for the core/query block that automatically filters
 * articles by the meeting_date custom meta field. This variation appears in the
 * block inserter as "Query: Filtered by Meeting Date".
 * 
 * When a user inserts this variation, it:
 * - Sets the post type to 'article'
 * - Configures default query parameters (10 posts per page)
 * - Sets the '__frmCustomFieldFilter' attribute to 'meeting_date' (used by filters below)
 * - Provides default innerBlocks with post title and excerpt
 * 
 * The actual filtering and sorting is handled by the filter functions below,
 * which check for this custom attribute and modify the query accordingly.
 * 
 * @hook get_block_type_variations - Filters block type variations during registration
 * 
 * @param array $variations Array of existing variations for the block type
 * @param WP_Block_Type $block_type The block type object (core/query in this case)
 * 
 * @return array Modified variations array with our custom variation added
 * 
 * @since 1.0.0
 */
if (!function_exists('fall_river_mirror_register_query_loop_variations')) {
    function fall_river_mirror_register_query_loop_variations( $variations, $block_type ) {
        // Only modify variations for the core/query block
        // This prevents affecting other block types that might use variations
        if ( 'core/query' !== $block_type->name ) {
            return $variations;
        }

        /**
         * Define the custom variation
         * 
         * This variation will appear in the block inserter when users search for
         * "meeting date", "filter", "articles", or "date".
         */
        $variations[] = array(
            'name'        => 'filtered-by-meeting-date',
            'title'       => __( 'Query: Filtered by Meeting Date', 'fall-river-mirror' ),
            'description' => __( 'Displays articles filtered by meeting_date custom field.', 'fall-river-mirror' ),
            'keywords'    => array( 'meeting date', 'filter', 'articles', 'date' ),
            'scope'       => array( 'inserter', 'block' ),
            'isDefault'   => false,
            'attributes'  => array(
                'query' => array(
                    'postType'             => 'article',
                    'perPage'              => 10,
                    'offset'               => 0,
                    'order'                => 'desc',
                    'inherit'              => false,
                    '__frmCustomFieldFilter' => 'meeting_date',
                ),
                '__frmCustomFieldFilter' => 'meeting_date',
            ),
            'innerBlocks' => array(
                array(
                    'core/post-template',
                    array(
                        array( 'core/post-title', array(
                            'level' => 2,
                            'isLink' => true,
                        ) ),
                        array( 'core/post-excerpt', array(
                            'excerptLength' => 25,
                        ) ),
                    ),
                ),
            ),
        );

        $variations[] = array(
            'name'        => 'filtered-by-view-count',
            'title'       => __( 'Query: Sorted by View Count', 'fall-river-mirror' ),
            'description' => __( 'Displays articles sorted by view count (most viewed first).', 'fall-river-mirror' ),
            'keywords'    => array( 'views', 'popular', 'view count', 'articles' ),
            'scope'       => array( 'inserter', 'block' ),
            'isDefault'   => false,
            'attributes'  => array(
                'query' => array(
                    'postType'             => 'article',
                    'perPage'              => 10,
                    'offset'               => 0,
                    'order'                => 'desc',
                    'inherit'              => false,
                    '__frmCustomFieldFilter' => '_article_view_count',
                ),
                '__frmCustomFieldFilter' => '_article_view_count',
            ),
            'innerBlocks' => array(
                array(
                    'core/post-template',
                    array(
                        'style'  => array(
                            'spacing' => array(
                                'blockGap' => 'var:preset|spacing|20',
                            ),
                        ),
                        'layout' => array( 'type' => 'default' ),
                    ),
                    array(
                        array(
                            'core/post-title',
                            array(
                                'textAlign'     => 'left',
                                'isLink'        => true,
                                'style'         => array(
                                    'spacing' => array(
                                        'margin'  => array( 'top' => '0', 'bottom' => '0' ),
                                        'padding' => array(
                                            'top'    => 'var:preset|spacing|20',
                                            'right'  => 'var:preset|spacing|20',
                                            'bottom' => 'var:preset|spacing|20',
                                            'left'   => 'var:preset|spacing|20',
                                        ),
                                    ),
                                ),
                                'backgroundColor' => 'very-light-gray',
                                'fontSize'        => 'medium',
                            ),
                            array(),
                        ),
                    ),
                ),
            ),
        );

        return $variations;
    }
}
add_filter( 'get_block_type_variations', 'fall_river_mirror_register_query_loop_variations', 10, 2 );

/**
 * Pass Query block's __frmCustomFieldFilter to inner blocks via context
 *
 * The query_loop_block_query_vars filter receives the Post Template block, not the
 * Query block, so our custom attribute is not available. This filter adds it to
 * the context when the parent is a Query block with our variation.
 *
 * @see https://github.com/WordPress/gutenberg/issues/60295
 */
if ( ! function_exists( 'fall_river_mirror_add_custom_field_filter_to_context' ) ) {
    function fall_river_mirror_add_custom_field_filter_to_context( $context, $parsed_block, $parent_block ) {
        if ( ! $parent_block || ! $parent_block->block_type || 'core/query' !== $parent_block->block_type->name ) {
            return $context;
        }
        $custom_filter = $parent_block->attributes['__frmCustomFieldFilter'] ?? null;
        if ( $custom_filter ) {
            $context['__frmCustomFieldFilter'] = $custom_filter;
        }
        return $context;
    }
}
add_filter( 'render_block_context', 'fall_river_mirror_add_custom_field_filter_to_context', 10, 3 );

/**
 * Modify Query Loop Block Query Variables for Meeting Date Filtering (Frontend)
 * 
 * This filter intercepts query variables for Query Loop blocks on the frontend
 * and modifies them to filter articles by the meeting_date custom meta field.
 * 
 * What this filter does:
 * 1. Checks if the query is for 'article' post type
 * 2. Attempts to detect if this is our specific variation (by checking for
 *    '__frmCustomFieldFilter' attribute)
 * 3. If detected (or if attribute is missing as fallback), applies:
 *    - meta_query filter to only show articles with meeting_date
 *    - orderby = 'meta_value' to sort by meeting_date
 *    - order = 'DESC' to show newest meeting dates first
 * 
 * This filter runs at priority 999 (very high) to ensure it executes after
 * other query modifications and takes precedence.
 * 
 * @hook query_loop_block_query_vars
 * 
 * @param array $query Array of query variables for WP_Query
 *                     Includes: post_type, orderby, order, meta_query, etc.
 * @param WP_Block $block The block instance containing attributes and parsed block data
 * 
 * @return array Modified query array with meeting_date filtering and sorting applied
 * 
 * @since 1.0.0
 * 
 * @see WP_Query for available query parameters
 * @see https://developer.wordpress.org/reference/hooks/query_loop_block_query_vars/
 */
if (!function_exists('fall_river_mirror_filter_query_loop_by_custom_field')) {
    function fall_river_mirror_filter_query_loop_by_custom_field( $query, $block ) {
        /**
         * Step 1: Validate post type
         * Only process queries for the 'article' post type
         */
        $post_type = $query['post_type'] ?? '';
        if ( $post_type !== 'article' && ( ! is_array( $post_type ) || ! in_array( 'article', $post_type ) ) ) {
            return $query; // Skip non-article queries
        }
        
        /**
         * Step 2: Detect variation
         *
         * The $block passed is the Post Template block (not the Query block). Get
         * __frmCustomFieldFilter from context (added by render_block_context) or attributes.
         */
        $custom_field_filter = $block->context['__frmCustomFieldFilter'] ?? null;
        if ( ! $custom_field_filter ) {
            $custom_field_filter = $block->attributes['__frmCustomFieldFilter'] ?? null;
        }
        if ( ! $custom_field_filter && isset( $block->parsed_block['attrs']['__frmCustomFieldFilter'] ) ) {
            $custom_field_filter = $block->parsed_block['attrs']['__frmCustomFieldFilter'];
        }

        /**
         * Step 3: Default to _article_meeting_date when no variation (basic Query block).
         * Matches editor behavior (rest_article_query) for frontend parity.
         */
        if ( ! $custom_field_filter ) {
            $custom_field_filter = '_article_meeting_date';
        }
        if ( ! in_array( $custom_field_filter, array( 'meeting_date', '_article_meeting_date', '_article_view_count' ), true ) ) {
            return $query;
        }

        /**
         * Step 4: Apply filtering and sorting based on variation
         */
        if ( $custom_field_filter === '_article_view_count' ) {
            $meta_key = '_article_view_count';
            $query['meta_query'] = array(
                array(
                    'key'     => $meta_key,
                    'compare' => 'EXISTS',
                ),
            );
            $query['orderby']  = 'meta_value_num';
            $query['meta_key'] = $meta_key;
            $query['order']    = 'DESC';
        } else {
            $meta_key = '_article_meeting_date';
            $query['meta_query'] = array(
                array(
                    'key'     => $meta_key,
                    'compare' => 'EXISTS',
                ),
            );
            $query['orderby']  = 'meta_value';
            $query['meta_key'] = $meta_key;
            $query['order']    = 'DESC';
        }

        return $query;
    }
}
add_filter( 'query_loop_block_query_vars', 'fall_river_mirror_filter_query_loop_by_custom_field', 999, 2 );

/**
 * Filter REST API Queries for Article Post Type (Editor/Admin)
 * 
 * The Gutenberg block editor uses WordPress REST API endpoints to fetch post data
 * for Query Loop blocks during editing. This filter ensures our meeting_date
 * filtering works consistently in both the editor and on the frontend.
 * 
 * Why this is needed:
 * - The editor queries posts via REST API (not direct WP_Query)
 * - The 'query_loop_block_query_vars' filter may not fire in editor context
 * - This filter intercepts REST API queries and applies the same filtering
 * 
 * Important limitations:
 * - This hook (rest_article_query) only fires for 'article' post type queries
 * - Block attributes are not available in REST API requests, so we cannot
 *   detect which specific variation is being used
 * - Therefore, this applies to ALL article query loop blocks in the editor
 * 
 * @hook rest_article_query
 * 
 * @param array $args Array of query arguments passed to WP_Query
 *                    These will be modified to include meta_query and sorting
 * @param WP_REST_Request $request The REST API request object
 *                                 Used to check request parameters like 'per_page'
 * 
 * @return array Modified query arguments with meeting_date filtering applied
 * 
 * @since 1.0.0
 * 
 * @see https://developer.wordpress.org/reference/hooks/rest_article_query/
 * @see WP_REST_Request for available request methods
 */
if (!function_exists('fall_river_mirror_filter_rest_article_query')) {
    function fall_river_mirror_filter_rest_article_query( $args, $request ) {
        /**
         * Step 1: Validate context
         * 
         * Only apply this filter in editor/admin context where REST API is used.
         * Frontend queries use the 'query_loop_block_query_vars' filter instead.
         * 
         * The REST_REQUEST constant is defined when WordPress is handling a REST API request.
         */
        if ( ! is_admin() && ! ( defined( 'REST_REQUEST' ) && REST_REQUEST ) ) {
            return $args; // Not in editor/admin context, skip
        }
        
        /**
         * Step 2: Detect query loop block queries
         *
         * Query Loop blocks send a 'per_page' parameter in REST API requests.
         * Regular REST API queries typically don't have this parameter, so we use
         * it as a signal that this is a Query Loop block query.
         */
        if ( ! $request->get_param( 'per_page' ) ) {
            return $args; // Not a Query Loop block query, skip
        }

        /**
         * Step 3: Apply filtering based on __frmCustomFieldFilter (from query param in editor).
         */
        $custom_filter = $request->get_param( '__frmCustomFieldFilter' );
        if ( $custom_filter === '_article_view_count' ) {
            $meta_key = '_article_view_count';
            $args['meta_key']   = $meta_key;
            $args['orderby']    = 'meta_value_num';
            $args['meta_query'] = array(
                array( 'key' => $meta_key, 'compare' => 'EXISTS' ),
            );
        } else {
            $meta_key = '_article_meeting_date';
            $args['meta_key']   = $meta_key;
            $args['orderby']    = 'meta_value';
            $args['meta_query'] = array(
                array( 'key' => $meta_key, 'compare' => 'EXISTS' ),
            );
        }
        $args['order'] = $request->get_param( 'order' ) ?? 'DESC';

        return $args;
    }
}
add_filter( 'rest_article_query', 'fall_river_mirror_filter_rest_article_query', 999, 2 );


