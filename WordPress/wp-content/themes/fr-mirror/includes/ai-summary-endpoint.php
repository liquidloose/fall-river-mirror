<?php

/**
 * FR Mirror AI Summary API Endpoint
 * Description: Adds a custom REST API endpoint to create summaries with title, HTML body, and image.
 * Version: 1.0
 */

add_action('rest_api_init', 'fr_mirror_summaries_api_endpoint');
function fr_mirror_summaries_api_endpoint() {
    register_rest_route('summaries/v2', '/enter-summary', array(
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
    // For now, it allows all requests because the JWT plugin checks the token on all endpoints automatically.
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

    // Add error handling and debugging
    if (is_wp_error($post_id)) {
        // If there's an error, return it
        wp_send_json_error(array(
            'message' => 'Post creation failed: ' . $post_id->get_error_message(),
            'data' => $post_data
        ), 500);
    } else if ($post_id == 0) {
        // If post ID is 0, the post wasn't created
        wp_send_json_error(array(
            'message' => 'Post creation failed - returned ID 0',
            'data' => $post_data
        ), 500);
    } else {
        // Log the successful post creation
        error_log('AI Summary post created with ID: ' . $post_id);
        // Continue with your success response
    }
}
