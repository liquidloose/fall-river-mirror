<?php
/**
 * This function registers a custom REST API endpoint for creating 'articles'.
 * It hooks into the 'rest_api_init' action to ensure it runs when the REST API is initialized.
 */
add_action( 'rest_api_init', function () {
  /**
   * register_rest_route() function.
   *
   * @param string $namespace The first part of the URL after /wp-json/.
   * @param string $route The base URL for the route.
   * @param array $args An array of options for the route.
   */
  register_rest_route( 'fr-mirror/v2', '/create-article', array(
    'methods' => 'POST',
    'callback' => 'create_article_callback',
    'permission_callback' => '__return_true',
    'args' => array(
      'title' => array(
        'required' => true,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'The title of the article.',
      ),
      'content' => array(
        'required' => true,
        'sanitize_callback' => 'wp_kses_post',
        'description' => 'The content of the article.',
      ),
      'status' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'The status of the article (e.g., "publish", "draft"). Defaults to "draft".',
      ),
    ),
  ) );
} );

/**
 * The callback function for the 'POST /articles' endpoint.
 *
 * This function handles the creation of a new article post.
 *
 * @param WP_REST_Request $request The request object.
 * @return WP_REST_Response|WP_Error The response object on success, or a WP_Error object on failure.
 */
function create_article_callback( WP_REST_Request $request ) {
  // Retrieve parameters from the request body.
  $title = $request->get_param( 'title' );
  $content = $request->get_param( 'content' );
  $status_param = $request->get_param( 'status' );
  $status = !empty($status_param) ? $status_param : 'draft'; // Default to 'publish'

  // Basic validation to ensure title and content are not empty.
  if ( empty( $title ) ) {
    return new WP_Error( 'no_title', 'A title is required to create an article.', array( 'status' => 400 ) );
  }
  if ( empty( $content ) ) {
    return new WP_Error( 'no_content', 'Content is required to create an article.', array( 'status' => 400 ) );
  }

  // Prepare the post data for insertion.
  $post_data = array(
    'post_title'    => $title,
    'post_content'  => $content,
    'post_type'     => 'article',
    'post_status'   => $status,
    'post_author'   => get_current_user_id(),
  );

  // Insert the post into the database.
  $post_id = wp_insert_post( $post_data, true );

  // Check if the post was created successfully.
  if ( is_wp_error( $post_id ) ) {
    return $post_id; // Return the WP_Error object.
  }

  // Prepare the response.
  $response_data = array(
      'id' => $post_id,
      'title' => get_the_title( $post_id ),
      'content' => get_post_field('post_content', $post_id),
      'status' => get_post_status( $post_id ),
      'link' => get_permalink( $post_id ),
      'message' => 'Article created successfully.'
  );

  // Return a success response with the new post data.
  return new WP_REST_Response( $response_data, 201 ); // 201 Created status code.
}

/**
 * Permission callback for the create article endpoint.
 *
 * This function checks if the current user has the capability to publish posts.
 * This is a crucial security measure to prevent unauthorized post creation.
 *
 * @return bool True if the user has permission, false otherwise.
 */
function create_article_permission_callback() {
    // Only allow users who can publish posts to create articles.
    // You can adjust the capability to 'edit_posts' or a custom capability if needed.
    return current_user_can( 'publish_posts' );
}
