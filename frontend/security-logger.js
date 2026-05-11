/**
 * Lightweight security logger for the frontend.
 *
 * - Loaded as a classic script (no module imports), exposing
 *   `window.securityLogger` so it works even when other scripts are loaded
 *   without `type="module"`.
 * - Avoids logging PII (usernames, file names, raw error stacks containing
 *   tokens) – only metadata that is useful for security review.
 * - The `process.env.NODE_ENV` reference from the previous version threw
 *   `ReferenceError` in browsers; we now feature-detect a "debug" hostname
 *   instead.
 */
(function (global) {
    const DEBUG_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);
    const isDebug = DEBUG_HOSTS.has(global.location && global.location.hostname);

    class SecurityLogger {
        constructor(maxEvents = 100) {
            this.events = [];
            this.maxEvents = maxEvents;
        }

        log(level, message, data = {}) {
            const safeData = sanitize(data);
            const event = {
                timestamp: new Date().toISOString(),
                level,
                message,
                data: safeData,
                url: global.location ? global.location.pathname : '',
            };
            this.events.push(event);
            if (this.events.length > this.maxEvents) this.events.shift();
            if (isDebug) {
                // eslint-disable-next-line no-console
                console.log(`[${level.toUpperCase()}] ${message}`, safeData);
            }
        }

        info(message, data) { this.log('info', message, data); }
        warn(message, data) { this.log('warn', message, data); }
        error(message, data) { this.log('error', message, data); }

        authAttempt(success /*, username */) {
            // Username intentionally omitted from persisted log to avoid PII.
            this.log('security', `Authentication ${success ? 'successful' : 'failed'}`, {
                success,
                type: 'auth_attempt',
            });
        }

        rateLimitExceeded(endpoint) {
            this.log('security', 'Rate limit exceeded', { endpoint, type: 'rate_limit' });
        }

        suspiciousActivity(activity, details) {
            this.log('security', `Suspicious activity: ${activity}`, {
                details: sanitize(details),
                type: 'suspicious',
            });
        }

        getEvents() { return [...this.events]; }
        clearEvents() { this.events = []; }
    }

    /**
     * Strip well-known sensitive fields so they never end up in the in-memory
     * security log (which could later be exfiltrated by an XSS payload).
     */
    function sanitize(data) {
        if (!data || typeof data !== 'object') return data;
        const blacklist = new Set(['password', 'token', 'access_token', 'authorization', 'username', 'filename']);
        const out = {};
        for (const key of Object.keys(data)) {
            if (blacklist.has(key.toLowerCase())) {
                out[key] = '[REDACTED]';
            } else {
                out[key] = data[key];
            }
        }
        return out;
    }

    global.securityLogger = new SecurityLogger();
})(typeof window !== 'undefined' ? window : globalThis);
