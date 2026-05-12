/**
 * ledger_node.js
 * Client-side "witness node" for the ScoreLedger blockchain.
 * Connects via Socket.IO, listens for new blocks, and updates
 * the Local Ledger Node widget in the bottom-left corner.
 * 
 * Auto-hides after 5 seconds of inactivity; reappears on new block.
 */
(function () {
    'use strict';

    // ---- DOM references ----
    const statusBadge   = document.getElementById('integrity-status');
    const blockCountEl  = document.getElementById('local-block-count');
    const lastHashEl    = document.getElementById('last-witnessed-hash');
    const widget        = document.querySelector('.ledger-node-widget');

    // ---- Local state ----
    let witnessedBlocks = 0;
    let lastHash        = null;
    let previousHash    = null;  // for lightweight chain validation
    let chainIntact     = true;
    let hideTimer       = null;

    // ---- Auto-hide logic ----
    function scheduleHide() {
        clearTimeout(hideTimer);
        // Never auto-hide if chain is broken — keep it visible as a warning
        if (!chainIntact) return;
        hideTimer = setTimeout(function () {
            if (widget) widget.classList.add('widget-hidden');
        }, 5000);
    }

    function showWidget() {
        if (widget) widget.classList.remove('widget-hidden');
        scheduleHide();
    }

    // ---- Helper: update UI ----
    function setStatus(text, bgClass) {
        if (!statusBadge) return;
        statusBadge.textContent = text;
        statusBadge.className   = 'badge ' + bgClass;
        statusBadge.style.fontSize = '0.6rem';
    }

    function renderBlock(hash) {
        if (blockCountEl)  blockCountEl.textContent = witnessedBlocks;
        if (lastHashEl)    lastHashEl.textContent   = hash
            ? '\u{1F517} ' + hash.substring(0, 16) + '...' + hash.substring(hash.length - 8)
            : 'Waiting for blocks\u2026';
    }

    // ---- Pulse animation on new block ----
    function pulseWidget() {
        if (!widget) return;
        widget.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease, opacity 0.5s ease, transform 0.5s ease';
        widget.style.boxShadow  = '0 0 18px rgba(0, 200, 255, 0.5)';
        widget.style.borderColor = 'rgba(0, 200, 255, 0.6)';
        setTimeout(function () {
            widget.style.boxShadow  = '0 8px 32px 0 rgba(0, 0, 0, 0.37)';
            widget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
        }, 800);
    }

    // ---- Boot: connect Socket.IO ----
    if (typeof io === 'undefined') {
        setStatus('Offline', 'bg-danger');
        if (lastHashEl) lastHashEl.textContent = 'Socket.IO not loaded';
        return;
    }

    var socket = io.connect(
        location.protocol + '//' + document.domain + ':' + location.port,
        { transports: ['websocket', 'polling'] }
    );

    // ---- Connection lifecycle ----
    socket.on('connect', function () {
        setStatus('Online', 'bg-success');
        if (witnessedBlocks === 0) {
            renderBlock(null);
        }
        // Ask server for current chain state
        socket.emit('request_ledger_state');
        // Start auto-hide timer on initial load
        scheduleHide();
    });

    socket.on('disconnect', function () {
        setStatus('Offline', 'bg-danger');
    });

    socket.on('connect_error', function () {
        setStatus('Error', 'bg-danger');
        if (lastHashEl) lastHashEl.textContent = 'Connection failed';
    });

    // ---- Receive initial ledger state (on connect / page load) ----
    socket.on('ledger_state', function (data) {
        if (data && typeof data.block_count === 'number') {
            witnessedBlocks = data.block_count;
            lastHash        = data.last_hash || null;
            previousHash    = data.prev_hash || null;
            chainIntact     = data.integrity !== false;

            renderBlock(lastHash);
            setStatus(
                chainIntact ? 'Verified' : 'Broken!',
                chainIntact ? 'bg-success' : 'bg-danger'
            );

            // If chain is broken on load, immediately show the widget
            if (!chainIntact) {
                showWidget();
            }
        }
    });

    // ---- Receive a new block broadcast ----
    socket.on('new_ledger_block', function (block) {
        if (!block) return;

        // Lightweight chain check: does the new block link to the previous?
        if (lastHash !== null && block.prev_hash !== lastHash) {
            chainIntact = false;
        }

        // Server-side integrity check (includes DB cross-reference)
        if (block.integrity === false) {
            chainIntact = false;
        }

        witnessedBlocks++;
        previousHash = lastHash;
        lastHash     = block.curr_hash;

        renderBlock(lastHash);
        setStatus(
            chainIntact ? 'Verified' : 'Broken!',
            chainIntact ? 'bg-success' : 'bg-danger'
        );
        pulseWidget();

        // Show widget on new block — stays visible if chain is broken
        showWidget();
    });
})();
