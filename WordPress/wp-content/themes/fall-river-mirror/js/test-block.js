wp.blocks.registerBlockType('rivedge/test-block', {
    title: 'Test Block',
    icon: 'smiley',
    category: 'common',
    edit: function() {
        return wp.element.createElement('div', {className: 'rivedge-test'}, 'Test Block (Editor)');
    },
    save: function() {
        return null; // Using render_callback for frontend
    }
});