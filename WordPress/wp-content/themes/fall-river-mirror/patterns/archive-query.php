<?php

/**
 * Title: Archive Query
 * Slug: fall-river-mirror/archive-query
 * Inserter: yes
 */

?>

<!-- wp:group {"tagName":"main","metadata":{"name":"Standard Sidebar Query Group"},"style":{"spacing":{"margin":{"bottom":"var:preset|spacing|40"},"padding":{"right":"0","left":"0"}}},"layout":{"type":"constrained","contentSize":"1200px"}} -->
<main class="wp-block-group" style="margin-bottom:var(--wp--preset--spacing--40);padding-right:0;padding-left:0"><!-- wp:columns {"style":{"spacing":{"blockGap":{"left":"var:preset|spacing|40"},"padding":{"right":"0","left":"0","top":"0","bottom":"0"}}},"backgroundColor":"very-light-gray"} -->
    <div class="wp-block-columns has-very-light-gray-background-color has-background" style="padding-top:0;padding-right:0;padding-bottom:0;padding-left:0"><!-- wp:column {"width":"66%"} -->
        <div class="wp-block-column" style="flex-basis:66%"><!-- wp:group {"className":"is-style-default","style":{"spacing":{"padding":{"right":"0","left":"var:preset|spacing|40","top":"0","bottom":"0"},"margin":{"top":"0","bottom":"var:preset|spacing|40"}}},"backgroundColor":"very-light-gray","layout":{"type":"flex","flexWrap":"nowrap"}} -->
            <div class="wp-block-group is-style-default has-very-light-gray-background-color has-background" style="margin-top:0;margin-bottom:var(--wp--preset--spacing--40);padding-top:0;padding-right:0;padding-bottom:0;padding-left:var(--wp--preset--spacing--40)"><!-- wp:group {"style":{"layout":{"selfStretch":"fill","flexSize":null},"spacing":{"blockGap":"0","padding":{"right":"0","left":"0"}}},"layout":{"type":"default"}} -->
                <div class="wp-block-group" style="padding-right:0;padding-left:0"><!-- wp:query {"queryId":1,"query":{"perPage":10,"pages":0,"offset":0,"postType":"article","order":"desc","orderBy":"date","author":"","search":"","exclude":[],"sticky":"","inherit":false,"parents":[],"format":[]},"metadata":{"categories":["posts"],"patternName":"core/fullwidth-posts-titles-with-dates","name":"Fullwidth posts titles with dates"},"align":"full","layout":{"type":"default"}} -->
                    <div class="wp-block-query alignfull"><!-- wp:post-template {"align":"full","style":{"typography":{"textTransform":"none"},"spacing":{"padding":{"top":"var:preset|spacing|40","bottom":"var:preset|spacing|40","left":"0","right":"0"},"margin":{"top":"0","bottom":"0"},"blockGap":"0"}},"layout":{"type":"constrained","contentSize":""}} -->
                        <!-- wp:group {"style":{"spacing":{"blockGap":"0","padding":{"bottom":"var:preset|spacing|50","left":"var:preset|spacing|40","right":"var:preset|spacing|40"}}},"backgroundColor":"paper","layout":{"type":"default"}} -->
                        <div class="wp-block-group has-paper-background-color has-background" style="padding-right:var(--wp--preset--spacing--40);padding-bottom:var(--wp--preset--spacing--50);padding-left:var(--wp--preset--spacing--40)"><!-- wp:group {"className":"is-style-default","style":{"border":{"bottom":{"color":"var:preset|color|contrast","width":"4px"}},"spacing":{"padding":{"top":"var:preset|spacing|30","right":"0","bottom":"var:preset|spacing|30","left":"0"},"blockGap":"0"}},"layout":{"type":"flex","flexWrap":"nowrap","justifyContent":"space-between"}} -->
                            <div class="wp-block-group is-style-default" style="border-bottom-color:var(--wp--preset--color--contrast);border-bottom-width:4px;padding-top:var(--wp--preset--spacing--30);padding-right:0;padding-bottom:var(--wp--preset--spacing--30);padding-left:0"><!-- wp:post-date {"textAlign":"left","format":"m.j","metadata":{"bindings":{"datetime":{"source":"core/post-data","args":{"field":"date"}}}},"style":{"spacing":{"margin":{"top":"0","right":"0","bottom":"0","left":"0"}},"elements":{"link":{"color":{"text":"var:preset|color|contrast"}}},"typography":{"letterSpacing":"1px","fontSize":"2rem","fontStyle":"normal","fontWeight":"600"}},"textColor":"contrast"} /-->

                                <!-- wp:post-date {"textAlign":"left","format":"Y","metadata":{"bindings":{"datetime":{"source":"core/post-data","args":{"field":"date"}}}},"style":{"spacing":{"margin":{"top":"0","right":"0","bottom":"0","left":"0"}},"elements":{"link":{"color":{"text":"var:preset|color|contrast"}}},"typography":{"letterSpacing":"1px","fontSize":"2rem","fontStyle":"normal","fontWeight":"600"}},"textColor":"contrast"} /-->
                            </div>
                            <!-- /wp:group -->

                            <!-- wp:post-title {"isLink":true,"style":{"layout":{"selfStretch":"fit"},"typography":{"lineHeight":"1.1","fontSize":"2.4rem","fontStyle":"normal","fontWeight":"400"},"elements":{"link":{"color":{"text":"var:preset|color|contrast"}}},"spacing":{"padding":{"top":"var:preset|spacing|30"}}},"textColor":"contrast","fontFamily":"roboto"} /-->
                        </div>
                        <!-- /wp:group -->
                        <!-- /wp:post-template -->

                        <!-- wp:group {"style":{"spacing":{"padding":{"right":"var:preset|spacing|40","left":"var:preset|spacing|40","bottom":"var:preset|spacing|40"},"margin":{"top":"0","bottom":"0"}}},"backgroundColor":"paper","layout":{"type":"default"}} -->
                        <div class="wp-block-group has-paper-background-color has-background" style="margin-top:0;margin-bottom:0;padding-right:var(--wp--preset--spacing--40);padding-bottom:var(--wp--preset--spacing--40);padding-left:var(--wp--preset--spacing--40)"><!-- wp:group {"style":{"spacing":{"padding":{"right":"0","left":"0","bottom":"0","top":"var:preset|spacing|40"},"margin":{"top":"0","bottom":"0"}}},"backgroundColor":"paper","layout":{"type":"default"}} -->
                            <div class="wp-block-group has-paper-background-color has-background" style="margin-top:0;margin-bottom:0;padding-top:var(--wp--preset--spacing--40);padding-right:0;padding-bottom:0;padding-left:0"><!-- wp:query-pagination {"style":{"elements":{"link":{"color":{"text":"var:preset|color|body-text"}}}},"backgroundColor":"paper","textColor":"body-text","layout":{"type":"flex","flexWrap":"nowrap","justifyContent":"space-between"}} -->
                                <!-- wp:query-pagination-previous {"style":{"typography":{"fontSize":"2rem","fontStyle":"normal","fontWeight":"600","textTransform":"uppercase","letterSpacing":"1px"}}} /-->

                                <!-- wp:query-pagination-next {"style":{"typography":{"fontSize":"2rem","fontStyle":"normal","fontWeight":"600","textTransform":"uppercase","letterSpacing":"1px"}}} /-->
                                <!-- /wp:query-pagination -->
                            </div>
                            <!-- /wp:group -->
                        </div>
                        <!-- /wp:group -->
                    </div>
                    <!-- /wp:query -->
                </div>
                <!-- /wp:group -->
            </div>
            <!-- /wp:group -->
        </div>
        <!-- /wp:column -->

        <!-- wp:column {"width":"33%","style":{"spacing":{"padding":{"top":"var:preset|spacing|40","bottom":"var:preset|spacing|40","right":"var:preset|spacing|40"}}},"backgroundColor":"very-light-gray"} -->
        <div class="wp-block-column has-very-light-gray-background-color has-background" style="padding-top:var(--wp--preset--spacing--40);padding-right:var(--wp--preset--spacing--40);padding-bottom:var(--wp--preset--spacing--40);flex-basis:33%"><!-- wp:group {"style":{"spacing":{"padding":{"right":"0","left":"0"},"blockGap":"0"},"position":{"type":"sticky","top":"0px"}},"backgroundColor":"very-light-gray","layout":{"type":"flex","flexWrap":"nowrap","justifyContent":"center","orientation":"horizontal","verticalAlignment":"top"}} -->
            <div class="wp-block-group has-very-light-gray-background-color has-background" style="padding-right:0;padding-left:0"><!-- wp:image {"id":1685,"sizeSlug":"large","linkDestination":"none"} -->
                <figure class="wp-block-image size-large"><img src="http://192.168.1.17:9004/wp-content/uploads/2026/01/Robot-artist-creating-a-bridge-painting-683x1024.png" alt="" class="wp-image-1685" /></figure>
                <!-- /wp:image -->
            </div>
            <!-- /wp:group -->
        </div>
        <!-- /wp:column -->
    </div>
    <!-- /wp:columns -->
</main>
<!-- /wp:group -->