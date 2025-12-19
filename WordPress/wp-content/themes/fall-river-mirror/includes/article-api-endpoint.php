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
      'journalists' => array(
        'required' => false,
        'sanitize_callback' => function( $value ) {
          if ( is_array( $value ) ) {
            return array_map( 'absint', $value );
          }
          return array();
        },
        'description' => 'Array of journalist post IDs.',
      ),
      'article_content' => array(
        'required' => false,
        'sanitize_callback' => 'wp_kses_post',
        'description' => 'The article content.',
      ),
      'committee' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'The committee name.',
      ),
      'youtube_id' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'The YouTube video ID.',
      ),
      'bullet_points' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_textarea_field',
        'description' => 'Bullet points or summary of the article.',
      ),
      'meeting_date' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'The meeting date.',
      ),
      'view_count' => array(
        'required' => false,
        'sanitize_callback' => 'absint',
        'description' => 'The view count for the associated video.',
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
  $status = !empty($status_param) ? $status_param : 'draft'; // Default to 'draft'

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

  // Save meta fields if provided
  $journalists = $request->get_param( 'journalists' );
  if ( ! empty( $journalists ) && is_array( $journalists ) ) {
    $sanitized_journalists = array_map( 'absint', $journalists );
    $sanitized_journalists = array_unique( $sanitized_journalists );
    update_post_meta( $post_id, '_article_journalists', $sanitized_journalists );
  }

  $article_content = $request->get_param( 'article_content' );
  if ( ! empty( $article_content ) ) {
    update_post_meta( $post_id, '_article_content', wp_kses_post( $article_content ) );
  }

  $committee = $request->get_param( 'committee' );
  if ( ! empty( $committee ) ) {
    update_post_meta( $post_id, '_article_committee', sanitize_text_field( $committee ) );
  }

  $youtube_id = $request->get_param( 'youtube_id' );
  if ( ! empty( $youtube_id ) ) {
    update_post_meta( $post_id, '_article_youtube_id', sanitize_text_field( $youtube_id ) );
  }

  $bullet_points = $request->get_param( 'bullet_points' );
  if ( ! empty( $bullet_points ) ) {
    update_post_meta( $post_id, '_article_bullet_points', sanitize_textarea_field( $bullet_points ) );
  }

  $meeting_date = $request->get_param( 'meeting_date' );
  if ( ! empty( $meeting_date ) ) {
    update_post_meta( $post_id, '_article_meeting_date', sanitize_text_field( $meeting_date ) );
  }

  $view_count = $request->get_param( 'view_count' );
  if ( ! empty( $view_count ) || $view_count === 0 ) {
    update_post_meta( $post_id, '_article_view_count', absint( $view_count ) );
  }

  // Prepare the response.
  $response_data = array(
      'id' => $post_id,
      'title' => get_the_title( $post_id ),
      'content' => get_post_field('post_content', $post_id),
      'status' => get_post_status( $post_id ),
      'link' => get_permalink( $post_id ),
      'message' => 'Article created successfully.',
      'meta' => array(
          'journalists' => get_post_meta( $post_id, '_article_journalists', true ),
          'article_content' => get_post_meta( $post_id, '_article_content', true ),
          'committee' => get_post_meta( $post_id, '_article_committee', true ),
          'youtube_id' => get_post_meta( $post_id, '_article_youtube_id', true ),
          'bullet_points' => get_post_meta( $post_id, '_article_bullet_points', true ),
          'meeting_date' => get_post_meta( $post_id, '_article_meeting_date', true ),
          'view_count' => get_post_meta( $post_id, '_article_view_count', true ),
      )
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
