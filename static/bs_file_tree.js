$(document).ready( function() {    
    $('#file_chooser').fileTree({ root: '/home', script: '/picardSpace/default/browse_bs_app_results' }, function(file) {
        window.location('none');
        //TODO window.location('/picardSpace/default/confirm_analysis_inputs');
        //alert(file);
    });
});
