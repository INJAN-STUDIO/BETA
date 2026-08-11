document.getElementById('send-btn').addEventListener('click', () => {
    const input = document.getElementById('user-input');
    const message = input.value;
    if (!message) return;
    
    console.log("Sending to B.E.T.A:", message);
    // Placeholder for API call
    input.value = '';
});
