<?php
// Add a custom REST API endpoint that returns "hello world"
function hello_world_api_endpoint() {
    // Register the route
    register_rest_route('custom/v1', '/hello', array(
        'methods' => 'GET',
        'callback' => 'hello_world_callback',
        'permission_callback' => '__return_true'
    ));
}

// Callback function for the endpoint
function hello_world_callback() {
    // Return a simple hello world response
    return array(
        'message' => 'hello world'
    );
}

// Hook into the rest_api_init action to register our endpoint
add_action('rest_api_init', 'hello_world_api_endpoint');
