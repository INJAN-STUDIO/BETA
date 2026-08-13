const chatBox = document.getElementById('chat-container');
const input = document.getElementById('user-input');

document.getElementById('menu-btn').addEventListener('click', () => document.getElementById('sidebar').classList.add('open'));

async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addBubble(text, 'user');
    input.value = '';
    input.style.height = 'auto';

    // Thinking indicator
    const thinking = document.createElement('div');
    thinking.className = 'dots';
    thinking.innerText = 'B.E.T.A is thinking';
    chatBox.appendChild(thinking);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        
        chatBox.removeChild(thinking);
        
        // Add AI bubble and stream text with spaces
        const aiBubble = addBubble("", 'ai');
        streamText(aiBubble, data.response);
    } catch (e) {
        chatBox.removeChild(thinking);
        addBubble("Error reaching B.E.T.A.", 'ai');
    }
}

function addBubble(text, className) {
    const div = document.createElement('div');
    div.className = `bubble ${className}`;
    div.innerText = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
}

function streamText(element, text) {
    let i = 0;
    const interval = setInterval(() => {
        // Ensure spaces are kept
        element.innerText = text.substring(0, i + 1);
        i++;
        chatBox.scrollTop = chatBox.scrollHeight;
        if (i >= text.length) clearInterval(interval);
    }, 20);
}

document.getElementById('send-btn').addEventListener('click', sendMessage);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }});
input.addEventListener('input', function() { this.style.height = 'auto'; this.style.height = (this.scrollHeight) + 'px'; });
