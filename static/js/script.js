document.addEventListener('DOMContentLoaded', function() {
    const changeColorBtn = document.getElementById('changeColorBtn');
    const body = document.body;
    
    // Array of background colors
    const colors = [
        '#f5f5f5', // Original color
        '#e6f7ff', // Light blue
        '#fff1e6', // Light orange
        '#f0f8e6', // Light green
        '#f7e6f7'  // Light purple
    ];
    
    let currentColorIndex = 0;
    
    // Function to change background color
    changeColorBtn.addEventListener('click', function() {
        currentColorIndex = (currentColorIndex + 1) % colors.length;
        body.style.backgroundColor = colors[currentColorIndex];
    });
    
    // Add a welcome message to console
    console.log('Welcome to My Flask App!');
});