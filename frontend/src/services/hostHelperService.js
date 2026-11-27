import axios from 'axios';

/**
 * Client for the AIDA host helper (tools/helper.py).
 * The helper is a small local HTTP service running on the host (not Docker)
 * that performs actions the browser cannot: opening folders in the file
 * explorer and launching aida.py in a new terminal window.
 */
const HELPER_URL = 'http://localhost:9876';

/**
 * Open a folder in the host's file explorer (Finder, Explorer, xdg-open).
 * The helper restricts paths to AIDA workspaces only.
 *
 * @param {string} path - Absolute path under the AIDA workspace tree
 * @returns {Promise<{success: boolean}>}
 */
export const openFolderOnHost = async (path) => {
    try {
        const response = await axios.post(`${HELPER_URL}/open`, { path }, {
            timeout: 3000,
        });
        return response.data;
    } catch (error) {
        if (error.code === 'ECONNREFUSED' || error.code === 'ERR_NETWORK') {
            throw new Error('Host helper not running. Start it with: python3 tools/helper.py');
        }
        throw error;
    }
};

/**
 * Check if the host helper is reachable.
 * @returns {Promise<boolean>}
 */
export const isHostHelperAvailable = async () => {
    try {
        await axios.get(`${HELPER_URL}/status`, { timeout: 1000 });
        return true;
    } catch {
        return false;
    }
};

/**
 * Assessment names the helper accepts (same rule as ASSESSMENT_NAME_RE in
 * tools/helper.py). For other names the UI only shows the command to copy.
 */
const LAUNCHABLE_NAME_RE = /^[A-Za-z0-9 _\-.]{1,128}$/;

export const canLaunchOnHost = (assessmentName) => LAUNCHABLE_NAME_RE.test(assessmentName || '');

/**
 * Quote one shell argument for the commands shown to copy: "name" like in
 * the docs, 'name' when double quotes wouldn't be literal.
 * @param {string} value
 * @returns {string}
 */
export const shellQuote = (value) => {
    if (!/["\\$`!]/.test(value)) return `"${value}"`;
    return `'${value.replace(/'/g, "'\\''")}'`;
};

/**
 * Command each launch mode runs (what the helper opens a terminal with).
 *   agent — Claude Code inside the assessment's own container (`aida run`)
 *   cli   — an AI CLI installed on this machine (`aida --assessment`)
 */
export const launchCommand = (assessmentName, mode = 'agent') => (
    mode === 'agent'
        ? `aida run ${shellQuote(assessmentName)}`
        : `aida --assessment ${shellQuote(assessmentName)}`
);

/**
 * Open a terminal window on the host running `launchCommand(name, mode)`.
 * Throws if the helper is unreachable or returns a non-2xx status.
 *
 * @param {string} assessmentName
 * @param {'agent'|'cli'} [mode='cli']
 * @returns {Promise<{success: boolean, error?: string}>}
 */
export const launchAidaOnHost = async (assessmentName, mode = 'cli') => {
    const response = await axios.post(
        `${HELPER_URL}/launch`,
        { assessment_name: assessmentName, mode },
        { timeout: 5000 },
    );
    return response.data;
};

/** Open a terminal running `aida run "<assessment>"` (sandboxed agent). */
export const launchAgentOnHost = (assessmentName) => launchAidaOnHost(assessmentName, 'agent');

// Backward-compat alias — old code still imports under the previous name
export const isFolderOpenerAvailable = isHostHelperAvailable;

export default {
    openFolderOnHost,
    isHostHelperAvailable,
    launchAidaOnHost,
    launchAgentOnHost,
    canLaunchOnHost,
    launchCommand,
};
