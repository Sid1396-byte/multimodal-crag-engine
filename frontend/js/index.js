marked.use(window.markedKatex({ throwOnError: false }));


        /* --- SPA VIEW SWITCHING LOGIC --- */
        let observerInitialized = false;
        let observer;

        function showArchitecture() {
            document.getElementById('view-chat').style.display = 'none';
            document.getElementById('view-architecture').style.display = 'block';
            document.getElementById('nav-chat-actions').style.display = 'none';
            document.getElementById('nav-arch-actions').style.display = 'flex';
            
            // Allow vertical scrolling for the architecture page
            document.body.style.overflowY = 'auto';
            document.body.style.overflowX = 'hidden';
            window.scrollTo({ top: 0, behavior: 'smooth' });

            // Initialize scroll animations
            if (!observerInitialized) {
                const nodes = document.querySelectorAll('.node');
                const observerOptions = { root: null, rootMargin: '0px', threshold: 0.15 };
                
                // 🚀 FIX: Removed the "unobserve" line so it animates every time!
                observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('visible');
                        } else {
                            entry.target.classList.remove('visible');
                        }
                    });
                }, observerOptions);
                
                nodes.forEach(node => observer.observe(node));
                observerInitialized = true;
            }
        }

        function showChat() {
            document.getElementById('view-architecture').style.display = 'none';
            document.getElementById('view-chat').style.display = 'flex';
            document.getElementById('nav-arch-actions').style.display = 'none';
            document.getElementById('nav-chat-actions').style.display = 'flex';
            
            // Lock scrolling to the specific chat containers
            document.body.style.overflow = 'hidden';
            window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        }

        /* --- CHAT WORKSPACE LOGIC --- */
        function escapeHTML(str) {
            if (!str) return '';
            return str.replace(/[&<>'"]/g, 
                tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag])
            );
        }

        let userId = "usr_" + crypto.randomUUID(); 
        
        // Wipe state if the user explicitly hard-refreshes (F5)
        const navEntries = performance.getEntriesByType("navigation");
        if (navEntries.length > 0 && navEntries[0].type === "reload") {
            localStorage.removeItem('truequery_sessions');
            localStorage.removeItem('truequery_activeSessionId');
            window.location.href = "/";
        }

        let sessions = JSON.parse(localStorage.getItem('truequery_sessions')) || {};
        let activeSessionId = localStorage.getItem('truequery_activeSessionId') || null;

        function saveState() {
            try {
                localStorage.setItem('truequery_sessions', JSON.stringify(sessions));
                localStorage.setItem('truequery_activeSessionId', activeSessionId);
            } catch (e) {
                console.warn('localStorage quota exceeded', e);
            }
        }

        function updateInputState() {
            const inputField = document.getElementById('chat-input');
            const sendBtn = document.getElementById('btn-send');
            
            if (sessions[activeSessionId] && sessions[activeSessionId].hasDocument) {
                inputField.disabled = false;
                sendBtn.disabled = false;
                inputField.placeholder = "Message TrueQuery...";
                inputField.focus();
            } else {
                inputField.disabled = true;
                sendBtn.disabled = true;
                inputField.placeholder = "Upload a document to unlock chat...";
            }
        }

        function createNewWorkspace() {
            activeSessionId = "sess_" + crypto.randomUUID();
            sessions[activeSessionId] = { title: "New Workspace", messages: [], hasDocument: false };
            saveState();
            renderHistoryList(); renderChatStream(); updateInputState();
        }

        function loadWorkspace(id) {
            activeSessionId = id;
            saveState();
            renderHistoryList(); renderChatStream(); updateInputState();
        }

        function deleteWorkspace(id, event) {
            event.stopPropagation(); 
            const li = event.target.closest('li');
            if (li) li.style.animation = 'fadeOutWorkspace 0.2s ease forwards';
            
            setTimeout(() => {
                delete sessions[id];
                
                if (activeSessionId === id) {
                    const keys = Object.keys(sessions);
                    if (keys.length > 0) loadWorkspace(keys[keys.length - 1]);
                    else createNewWorkspace();
                } else {
                    saveState();
                    renderHistoryList();
                }
            }, 180);
        }

        function renderHistoryList() {
            const list = document.getElementById("history-list");
            list.innerHTML = "";
            Object.keys(sessions).reverse().forEach(id => {
                const li = document.createElement("li");
                li.className = `history-item ${id === activeSessionId ? 'active' : ''}`;
                li.innerHTML = `
                    <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${sessions[id].title}</span>
                    <span class="delete-btn" onclick="deleteWorkspace('${id}', event)">&times;</span>
                `;
                li.onclick = (e) => { if(e.target.className !== 'delete-btn') loadWorkspace(id); };
                list.appendChild(li);
            });
        }

        function renderChatStream() {
            const stream = document.getElementById("chat-stream");
            stream.innerHTML = "";
            
            if (sessions[activeSessionId].messages.length === 0) {
                stream.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line></svg>
                        </div>
                        <h2>Workspace Initialized</h2>
                        <p>Attach a document payload to generate the high-dimensional vector index and unlock the conversational agent.</p>
                    </div>
                `;
                return;
            }

            sessions[activeSessionId].messages.forEach(m => stream.insertAdjacentHTML('beforeend', m.html));
            stream.scrollTop = stream.scrollHeight;
            if(window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise();
        }

        if (Object.keys(sessions).length === 0) {
            createNewWorkspace();
        } else {
            renderHistoryList();
            renderChatStream();
            updateInputState();
        }

        window.togglePanel = function(btnId, targetPanelId, otherPanelId, otherBtnId) {
            const targetPanel = document.getElementById(targetPanelId);
            const otherPanel = document.getElementById(otherPanelId);
            const btn = document.getElementById(btnId);
            const otherBtn = document.getElementById(otherBtnId);
            
            if(otherPanel && otherPanel.classList.contains('open')) {
                otherPanel.classList.remove('open');
                if(otherBtn) otherBtn.classList.remove('active-blue');
            }
            
            targetPanel.classList.toggle('open');
            if(btn) btn.classList.toggle('active-blue');
            
            setTimeout(() => {
                const stream = document.getElementById("chat-stream");
                stream.scrollTop = stream.scrollHeight;
            }, 50);
        }

        window.toggleSubPanel = function(panelId) { document.getElementById(panelId).classList.toggle('open'); }

        document.getElementById('hidden-file').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if(!file) return;
            const formData = new FormData();
            formData.append('file', file);
            formData.append('session_id', activeSessionId); 

            const stream = document.getElementById('chat-stream');
            const tid = Date.now();
            
            if(sessions[activeSessionId].messages.length === 0) stream.innerHTML = "";

            stream.insertAdjacentHTML('beforeend', `
                <div class="ai-msg" id="up-${tid}">
                    <div class="avatar-ai"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></div>
                    <div class="ai-content-body"><span class="loading-pulse">📤 Ingesting layout topology to Workspace Isolated Index...</span></div>
                </div>`);
            stream.scrollTop = stream.scrollHeight;
            
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                document.getElementById(`up-${tid}`).innerHTML = `<div class="avatar-ai" style="background:var(--accent-green); box-shadow: 0 0 15px var(--accent-green-glow);">✓</div><div class="ai-content-body" style="color:var(--accent-green); font-weight: 600;">${data.message}</div>`;
                sessions[activeSessionId].messages.push({ id: `up-${tid}`, html: document.getElementById(`up-${tid}`).outerHTML });
                
                sessions[activeSessionId].hasDocument = true;
                saveState();
                updateInputState();

            } catch (err) {
                document.getElementById(`up-${tid}`).innerHTML = `<div class="ai-content-body" style="color:#ef4444; font-weight:bold;">Error uploading document.</div>`;
            }
        });

        const input = document.getElementById('chat-input');
        input.addEventListener('keypress', (e) => { if(e.key === 'Enter' && !input.disabled) { e.preventDefault(); executeQuery(); } });

        async function executeQuery() {
            const text = input.value.trim();
            if(!text) return;

            const userHtml = `<div class="msg-block user-msg"><div class="msg-content">${escapeHTML(text)}</div></div>`;
            const msgIdUser = "msg_" + Date.now();
            sessions[activeSessionId].messages.push({ id: msgIdUser, html: userHtml });
            
            if (sessions[activeSessionId].title === "New Workspace") sessions[activeSessionId].title = text.substring(0, 25) + "...";
            saveState();
            renderHistoryList(); renderChatStream();
            input.value = '';

            const stream = document.getElementById('chat-stream');
            const tid = Date.now();
            stream.insertAdjacentHTML('beforeend', `
                <div class="ai-msg" id="ai-${tid}">
                    <div class="avatar-ai"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></div>
                    <div class="ai-content-body"><span class="loading-pulse">Executing Isolated Graph Retrieval...</span></div>
                </div>`);
            stream.scrollTop = stream.scrollHeight;

            const form = new FormData();
            form.append('question', text);
            form.append('session_id', activeSessionId); 

            try {
                const res = await fetch('/api/query', { method: 'POST', body: form });
                const data = await res.json();

                const logsHtml = data.pipeline_logs.map(log => `<div class="trace-row">${escapeHTML(log)}</div>`).join('');
                
                const subQueriesHtml = (data.sub_queries && data.sub_queries.length > 0) 
                    ? `<div class="chunk-group">
                        <div class="chunk-header" style="color: var(--accent-purple);" onclick="toggleSubPanel('sub-queries-${tid}')">
                            <span>[+] Query Decomposition (${data.sub_queries.length} Targets)</span>
                        </div>
                        <div class="chunk-list custom-scroll" id="sub-queries-${tid}">
                            ${data.sub_queries.map((sq, i) => `<div class="chunk-card" style="border-left-color: var(--accent-purple);"><strong>[Target ${i+1}]</strong> ${escapeHTML(sq)}</div>`).join('')}
                        </div>
                       </div>` 
                    : '';

                const rawChunksHtml = data.all_chunks.map((c, i) => `<div class="chunk-card"><strong>[Chunk ${i+1}]</strong> ${escapeHTML(c).substring(0, 200)}...</div>`).join('');
                const topChunksHtml = data.top_chunks.map((c, i) => `<div class="chunk-card winner"><strong>[Winner ${i+1}]</strong> ${escapeHTML(c).substring(0, 250)}...</div>`).join('');
                
                const parsedAnswer = marked.parse(data.answer);

                const aiResponseHtml = `
                    <div class="ai-msg" id="ai-final-${tid}">
                        <div class="avatar-ai"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></div>
                        <div class="ai-content-body">
                            <div class="markdown-body">${parsedAnswer}</div>
                            
                            <div class="action-row">
                                <div class="pill-btn" id="btn-logs-${tid}" onclick="togglePanel('btn-logs-${tid}', 'panel-logs-${tid}', 'panel-eval-${tid}', 'btn-eval-${tid}')">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
                                    Pipeline Logs
                                </div>
                                <div class="pill-btn" id="btn-eval-${tid}" onclick="togglePanel('btn-eval-${tid}', 'panel-eval-${tid}', 'panel-logs-${tid}', 'btn-logs-${tid}')">
                                    <span class="status-dot" id="eval-dot-${tid}" style="background:var(--node-orange); animation:pulse 1s infinite;"></span> 
                                    <span id="eval-text-${tid}">Evaluating Safety...</span>
                                </div>
                                
                                <div style="margin-left:auto; display:flex; gap:16px; font-size:0.75rem; color:var(--text-secondary); align-items:center; font-weight:600; padding:6px 12px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05); box-shadow:var(--shadow-sunken);">
                                    <span>⏱️ ${data.total_time}s</span>
                                    <span>🪙 ${data.total_tokens} Tokens</span>
                                </div>
                            </div>

                            <div class="expand-panel" id="panel-logs-${tid}">
                                <div class="panel-header"><span class="check-icon" style="color:var(--accent-blue);">✓</span> LangGraph Trace Matrix</div>
                                <div style="background: rgba(0,0,0,0.4); padding: 10px 0;">
                                    ${logsHtml}
                                </div>
                                
                                ${subQueriesHtml}
                                
                                <div class="chunk-group">
                                    <div class="chunk-header" onclick="toggleSubPanel('raw-list-${tid}')">
                                        <span>[+] Qdrant Hybrid Retrieval (${data.all_chunks.length} Chunks)</span>
                                        <span style="color:var(--text-secondary);">${data.retrieval_time}s</span>
                                    </div>
                                    <div class="chunk-list custom-scroll" id="raw-list-${tid}">${rawChunksHtml}</div>
                                </div>
                                <div class="chunk-group">
                                    <div class="chunk-header green" onclick="toggleSubPanel('top-list-${tid}')">
                                        <span>[+] Cohere Rerank Winners (${data.top_chunks.length} Chunks)</span>
                                        <span style="color:var(--text-secondary);">${data.rerank_time}s</span>
                                    </div>
                                    <div class="chunk-list custom-scroll" id="top-list-${tid}">${topChunksHtml}</div>
                                </div>
                            </div>
                            
                            <div class="expand-panel" id="panel-eval-${tid}">
                                <div class="panel-header" id="eval-result-text-${tid}">
                                    <span class="loading-pulse">Calculating DeepEval Metrics...</span>
                                </div>
                            </div>
                        </div>
                    </div>`;

                document.getElementById(`ai-${tid}`).outerHTML = aiResponseHtml;
                stream.scrollTop = stream.scrollHeight;
                if(window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([document.getElementById(`ai-final-${tid}`)]);
                sessions[activeSessionId].messages.push({ id: tid, html: document.getElementById(`ai-final-${tid}`).outerHTML });
                saveState();

                const evalForm = new FormData();
                evalForm.append('question', text);
                evalForm.append('generation', data.answer);
                evalForm.append('contexts', data.documents);

                fetch('/api/evaluate', { method: 'POST', body: evalForm })
                    .then(r => r.json())
                    .then(evalData => {
                        const evalBtn = document.getElementById(`btn-eval-${tid}`);
                        document.getElementById(`eval-dot-${tid}`).style.background = 'var(--accent-green)';
                        document.getElementById(`eval-dot-${tid}`).style.animation = 'none';
                        document.getElementById(`eval-text-${tid}`).innerText = "DeepEval Verified";
                        evalBtn.style.color = "var(--text-primary)";
                        
                        const evalPanel = document.getElementById(`panel-eval-${tid}`);
                        if(evalPanel) {
                            evalPanel.innerHTML = `
                                <div class="panel-header" style="border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(16,185,129,0.05);">
                                    <span class="check-icon" style="color:var(--accent-green);">✓</span> DeepEval Security Grounding
                                </div>
                                <div style="padding: 20px; font-size:0.85rem; background: rgba(0,0,0,0.3);">
                                    <div style="display:flex; justify-content:space-between; font-weight:700; margin-bottom: 6px; font-size:0.9rem;">
                                        <span>Answer Relevancy</span><span style="color:var(--accent-green); text-shadow:0 0 10px var(--accent-green-glow);">${evalData.answer_relevancy} / 1.0</span>
                                    </div>
                                    <div style="color:var(--text-secondary); margin-bottom:24px; border-left:3px solid var(--border-glass); padding-left:14px; font-style:italic; line-height:1.6;">
                                        "${escapeHTML(evalData.relevancy_reason)}"
                                    </div>

                                    <div style="display:flex; justify-content:space-between; font-weight:700; margin-bottom: 6px; font-size:0.9rem;">
                                        <span>Fact Faithfulness</span><span style="color:var(--accent-green); text-shadow:0 0 10px var(--accent-green-glow);">${evalData.faithfulness} / 1.0</span>
                                    </div>
                                    <div style="color:var(--text-secondary); border-left:3px solid var(--border-glass); padding-left:14px; font-style:italic; line-height:1.6;">
                                        "${escapeHTML(evalData.faithfulness_reason)}"
                                    </div>
                                </div>
                            `;
                        }
                        
                        const msgIndex = sessions[activeSessionId].messages.findIndex(m => m.id === tid);
                        if(msgIndex !== -1) {
                            sessions[activeSessionId].messages[msgIndex].html = document.getElementById(`ai-final-${tid}`).outerHTML;
                            saveState();
                        }
                    });

            } catch(err) {
                document.getElementById(`ai-${tid}`).innerHTML = `<div class="ai-content-body" style="color:#ef4444; font-weight:bold;">Pipeline execution fault.</div>`;
            }
        }
        
        window.addEventListener('DOMContentLoaded', async (event) => {
            try {
                const res = await fetch('/api/boot_id');
                const data = await res.json();
                const savedBootId = localStorage.getItem('truequery_boot_id');
                
                if (savedBootId && savedBootId !== data.boot_id) {
                    console.log("Server restarted. Wiping stale client state.");
                    localStorage.removeItem('truequery_sessions');
                    localStorage.removeItem('truequery_activeSessionId');
                    localStorage.setItem('truequery_boot_id', data.boot_id);
                    window.location.href = "/";
                    return;
                } else if (!savedBootId) {
                    localStorage.setItem('truequery_boot_id', data.boot_id);
                }
            } catch (e) {
                console.warn('Could not fetch boot_id', e);
            }

            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('view') === 'architecture') {
                showArchitecture();
            }
        });