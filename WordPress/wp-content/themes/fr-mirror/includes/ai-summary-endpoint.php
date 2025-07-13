<?php

/**
 * FR Mirror AI Summary API Endpoint
 * Description: Adds a custom REST API endpoint to create summaries with title, HTML body, and image.
 * Version: 1.0
 */

add_action('rest_api_init', 'fr_mirror_summaries_api_endpoint');
function fr_mirror_summaries_api_endpoint() {
    register_rest_route('summaries/v1', '/enter-summary', array(
        'methods' => 'POST',
        'callback' => 'fr_mirror_summaries_callback',
        'permission_callback' => 'fr_mirror_summaries_api_authentication',
        'args' => array(
            'title' => array(
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ),
            'body' => array(
                'required' => false,
                'sanitize_callback' => 'wp_kses_post',
            ),
            'image' => array(
                'required' => false,
                'sanitize_callback' => 'esc_url_raw',
            ),
        ),
    ));
}


/**
 * Permission callback for the custom REST API endpoint.
 * This function can be used to implement authentication if needed.
 * For now, it allows all requests.
 *
 * @return bool
 */

function fr_mirror_summaries_api_authentication($request) {
    // This function can be used to implement authentication if needed.
    // For now, it allows all requests.
    return true;
}


/**
 * Callback function for the custom REST API endpoint.
 * It creates a new post with the provided title, body, and image.
 *
 * @param WP_REST_Request $request The request object.
 * @return array The response data.
 */

function fr_mirror_summaries_callback($request) {
    // Get parameters from request
    $title = $request->get_param('title');
    $body = $request->get_param('body');
    $image = $request->get_param('image');

    // Create post
    $post_data = array(
        'post_title'    => sanitize_text_field($title),
        'post_content'  => wp_kses_post($body),
        'post_status'   => 'publish',
        'post_type'     => 'article',
    );

    // Insert the post into the database
    $post_id = wp_insert_post($post_data);

    // Check if post was created successfully
    if (!is_wp_error($post_id)) {
        // If image URL is provided, set it as the featured image
        if (!empty($image)) {
            // Set the featured image URL as post meta
            update_post_meta($post_id, '_thumbnail_url', esc_url_raw($image));

            // You might also want to add a custom field to display the image in your theme
            update_post_meta($post_id, 'featured_image_url', esc_url_raw($image));
        }

        return array(
            'success' => true,
            'message' => 'Article created successfully',
            'post_id' => $post_id
        );
    } else {
        return array(
            'success' => false,
            'message' => $post_id->get_error_message()
        );
    }
}
