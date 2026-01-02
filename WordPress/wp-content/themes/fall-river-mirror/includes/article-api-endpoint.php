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
      'journalist_name' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'Journalist name (e.g., "Aurelius Stone") to match to existing journalist by first_name + last_name.',
      ),
      'article_content' => array(
        'required' => true,
        'sanitize_callback' => 'wp_kses_post',
        'description' => 'The article content (maps to _article_content custom field).',
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
      'featured_image' => array(
        'required' => false,
        'sanitize_callback' => 'sanitize_text_field',
        'description' => 'Base64-encoded PNG/JPG image data (data:image/png;base64,... or data:image/jpeg;base64,...) or URL to PNG/JPG image.',
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
  $article_content = $request->get_param( 'article_content' );
  $status_param = $request->get_param( 'status' );
  $status = !empty($status_param) ? $status_param : 'draft'; // Default to 'draft'

  // Basic validation to ensure title and article_content are not empty.
  if ( empty( $title ) ) {
    return new WP_Error( 'no_title', 'A title is required to create an article.', array( 'status' => 400 ) );
  }
  if ( empty( $article_content ) ) {
    return new WP_Error( 'no_article_content', 'Article content is required to create an article.', array( 'status' => 400 ) );
  }

  // Prepare the post data for insertion.
  // Note: article_content maps to _article_content custom field, not post_content
  $post_data = array(
    'post_title'    => $title,
    'post_content'  => '', // Leave post_content empty, article_content goes to custom field
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

  // Handle journalist associations
  $journalist_ids = array();
  
  // Support journalist IDs (array)
  $journalists = $request->get_param( 'journalists' );
  if ( ! empty( $journalists ) && is_array( $journalists ) ) {
    $journalist_ids = array_map( 'absint', $journalists );
  }
  
  // Support journalist name (string) - match to existing journalist
  $journalist_name = $request->get_param( 'journalist_name' );
  if ( ! empty( $journalist_name ) ) {
    $name = trim( sanitize_text_field( $journalist_name ) );
    $name_parts = preg_split( '/\s+/', $name );
    
    if ( count( $name_parts ) >= 2 ) {
      $first_name = $name_parts[0];
      $last_name = $name_parts[count( $name_parts ) - 1];
      
      // Query for journalist matching first_name and last_name
      $journalist_query = new WP_Query( array(
        'post_type' => 'journalist',
        'posts_per_page' => 1,
        'meta_query' => array(
          'relation' => 'AND',
          array(
            'key' => '_journalist_first_name',
            'value' => $first_name,
            'compare' => '='
          ),
          array(
            'key' => '_journalist_last_name',
            'value' => $last_name,
            'compare' => '='
          )
        )
      ) );
      
      if ( $journalist_query->have_posts() ) {
        $found_journalist_id = $journalist_query->posts[0]->ID;
        $journalist_ids[] = $found_journalist_id;
        error_log( 'Found journalist: ' . $name . ' (ID: ' . $found_journalist_id . ')' );
      } else {
        error_log( 'Journalist not found: ' . $name . ' (first: ' . $first_name . ', last: ' . $last_name . ')' );
      }
    }
  }
  
  // Save unique journalist IDs
  if ( ! empty( $journalist_ids ) ) {
    $journalist_ids = array_unique( $journalist_ids );
    $journalist_ids = array_values( $journalist_ids ); // Re-index array to ensure proper JSON encoding
    // Ensure all values are integers
    $journalist_ids = array_map( 'absint', $journalist_ids );
    $journalist_ids = array_filter( $journalist_ids ); // Remove any zeros
    $journalist_ids = array_values( $journalist_ids ); // Re-index again
    
    if ( ! empty( $journalist_ids ) ) {
      $result = update_post_meta( $post_id, '_article_journalists', $journalist_ids );
      error_log( 'Saved journalists to article ' . $post_id . ': ' . print_r( $journalist_ids, true ) . ' (result: ' . var_export( $result, true ) . ')' );
      
      // Verify it was saved correctly
      $saved = get_post_meta( $post_id, '_article_journalists', true );
      error_log( 'Verified saved journalists for article ' . $post_id . ': ' . print_r( $saved, true ) );
    }
  } else {
    error_log( 'No journalist IDs to save for article ' . $post_id );
  }

  // Save article_content to _article_content custom field
  if ( ! empty( $article_content ) ) {
    update_post_meta( $post_id, '_article_content', wp_kses_post( $article_content ) );
  }

  $committee = $request->get_param( 'committee' );
  if ( ! empty( $committee ) ) {
    // Save committee as meta field (for backward compatibility)
    update_post_meta( $post_id, '_article_committee', sanitize_text_field( $committee ) );
    
    // Create category if it doesn't exist and assign it to the post
    $sanitized_committee = sanitize_text_field( $committee );
    
    // Check if category already exists
    $category = get_term_by( 'name', $sanitized_committee, 'category' );
    
    if ( ! $category ) {
      // Category doesn't exist, create it using wp_insert_term
      $category_result = wp_insert_term( $sanitized_committee, 'category' );
      
      if ( is_wp_error( $category_result ) ) {
        // Log error but don't fail the request
        error_log( 'Failed to create committee category: ' . $category_result->get_error_message() );
      } else {
        // Category created successfully, get the term_id and assign it to the post
        $category_id = isset( $category_result['term_id'] ) ? $category_result['term_id'] : $category_result;
        wp_set_post_categories( $post_id, array( $category_id ), false );
      }
    } else {
      // Category exists, assign it to the post
      wp_set_post_categories( $post_id, array( $category->term_id ), false );
    }
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

  // Handle featured image if provided
  $featured_image = $request->get_param( 'featured_image' );
  if ( ! empty( $featured_image ) ) {
    $attachment_id = null;
    
    // Check if it's a base64 encoded image (PNG or JPG)
    if ( preg_match( '/^data:image\/(png|jpeg|jpg);base64,/', $featured_image, $matches ) ) {
      // Extract image type and base64 data
      $image_type = $matches[1];
      $image_data = preg_replace( '/^data:image\/(png|jpeg|jpg);base64,/', '', $featured_image );
      $image_data = base64_decode( $image_data );
      
      if ( $image_data !== false ) {
        // Determine file extension and mime type
        $extension = ( $image_type === 'png' ) ? 'png' : 'jpg';
        $mime_type = ( $image_type === 'png' ) ? 'image/png' : 'image/jpeg';
        
        // Generate filename
        $filename = 'article-' . $post_id . '-' . time() . '.' . $extension;
        $upload_dir = wp_upload_dir();
        $file_path = $upload_dir['path'] . '/' . $filename;
        
        // Save image to uploads directory
        file_put_contents( $file_path, $image_data );
        
        // Prepare attachment data
        $attachment = array(
          'post_mime_type' => $mime_type,
          'post_title'     => sanitize_file_name( pathinfo( $filename, PATHINFO_FILENAME ) ),
          'post_content'   => '',
          'post_status'    => 'inherit'
        );
        
        // Insert attachment
        $attachment_id = wp_insert_attachment( $attachment, $file_path, $post_id );
        
        if ( ! is_wp_error( $attachment_id ) ) {
          // Generate attachment metadata
          require_once( ABSPATH . 'wp-admin/includes/image.php' );
          $attach_data = wp_generate_attachment_metadata( $attachment_id, $file_path );
          wp_update_attachment_metadata( $attachment_id, $attach_data );
          
          // Set as featured image
          set_post_thumbnail( $post_id, $attachment_id );
        } else {
          error_log( 'Failed to create attachment: ' . $attachment_id->get_error_message() );
        }
      }
    } elseif ( filter_var( $featured_image, FILTER_VALIDATE_URL ) ) {
      // It's a URL - download and upload the image
      $image_url = esc_url_raw( $featured_image );
      
      // Download image
      $response = wp_remote_get( $image_url );
      
      if ( ! is_wp_error( $response ) && wp_remote_retrieve_response_code( $response ) === 200 ) {
        $image_data = wp_remote_retrieve_body( $response );
        $image_type = wp_remote_retrieve_header( $response, 'content-type' );
        
        // Determine if it's PNG or JPG based on content-type or URL extension
        $is_png = ( $image_type === 'image/png' || preg_match( '/\.png$/i', $image_url ) );
        $is_jpg = ( $image_type === 'image/jpeg' || $image_type === 'image/jpg' || preg_match( '/\.(jpg|jpeg)$/i', $image_url ) );
        
        if ( $is_png || $is_jpg ) {
          // Determine file extension and mime type
          $extension = $is_png ? 'png' : 'jpg';
          $mime_type = $is_png ? 'image/png' : 'image/jpeg';
          
          // Generate filename from URL or use default
          $filename = basename( parse_url( $image_url, PHP_URL_PATH ) );
          if ( empty( $filename ) || ! preg_match( '/\.(png|jpg|jpeg)$/i', $filename ) ) {
            $filename = 'article-' . $post_id . '-' . time() . '.' . $extension;
          } else {
            // Ensure correct extension
            $filename = preg_replace( '/\.(png|jpg|jpeg)$/i', '.' . $extension, $filename );
          }
          
          $upload_dir = wp_upload_dir();
          $file_path = $upload_dir['path'] . '/' . sanitize_file_name( $filename );
          
          // Save image
          file_put_contents( $file_path, $image_data );
          
          // Prepare attachment data
          $attachment = array(
            'post_mime_type' => $mime_type,
            'post_title'     => sanitize_file_name( pathinfo( $filename, PATHINFO_FILENAME ) ),
            'post_content'   => '',
            'post_status'    => 'inherit'
          );
          
          // Insert attachment
          $attachment_id = wp_insert_attachment( $attachment, $file_path, $post_id );
          
          if ( ! is_wp_error( $attachment_id ) ) {
            // Generate attachment metadata
            require_once( ABSPATH . 'wp-admin/includes/image.php' );
            $attach_data = wp_generate_attachment_metadata( $attachment_id, $file_path );
            wp_update_attachment_metadata( $attachment_id, $attach_data );
            
            // Set as featured image
            set_post_thumbnail( $post_id, $attachment_id );
          } else {
            error_log( 'Failed to create attachment from URL: ' . $attachment_id->get_error_message() );
          }
        } else {
          error_log( 'Unsupported image type from URL. Expected PNG or JPG, got: ' . $image_type );
        }
      } else {
        error_log( 'Failed to download image from URL: ' . $image_url );
      }
    }
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
          '_article_journalists' => get_post_meta( $post_id, '_article_journalists', true ),
          '_article_content' => get_post_meta( $post_id, '_article_content', true ),
          '_article_committee' => get_post_meta( $post_id, '_article_committee', true ),
          '_article_youtube_id' => get_post_meta( $post_id, '_article_youtube_id', true ),
          '_article_bullet_points' => get_post_meta( $post_id, '_article_bullet_points', true ),
          '_article_meeting_date' => get_post_meta( $post_id, '_article_meeting_date', true ),
          '_article_view_count' => get_post_meta( $post_id, '_article_view_count', true ),
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
