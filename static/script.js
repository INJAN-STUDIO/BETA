document.getElementById('send-btn').addEventListener('click', async () => {
    const input = document.getElementById('user-input');
    const message = input.value;
    if (!message) return;
    
    // Add user message to UI
    appendMessage("You", message);
    input.value = '';
    
    // Send to our new backend
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        
        // Show AI response
        appendMessage("B.E.T.A", data.response);
        
        // Play audio if available
        if (data.audio_url) {
            const audio = new Audio(data.audio_url);
            audio.play();
        }
    } catch (error) {
        console.error("Error talking to B.E.T.A:", error);
    }
});

function appendMessage(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    msgDiv.innerHTML = `<strong>${sender}:</strong> ${text}`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}
