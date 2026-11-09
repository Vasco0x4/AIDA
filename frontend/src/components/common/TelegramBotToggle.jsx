/**
 * Self-contained toggle to enable inbound Telegram bot control.
 * Reads/writes the `telegram_bot_enabled` platform setting directly.
 */
import React, { useEffect, useState } from 'react';
import apiClient from '../../services/api';

export default function TelegramBotToggle() {
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    apiClient.get('/system/settings/telegram_bot_enabled')
      .then(({ data }) => setEnabled(String(data.value).toLowerCase() === 'true'))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const toggle = async (e) => {
    const v = e.target.checked;
    setEnabled(v);
    try {
      await apiClient.put('/system/settings/telegram_bot_enabled', { value: v ? 'true' : 'false' });
    } catch {
      setEnabled(!v);
    }
  };

  return (
    <div className="mt-2 pt-2 border-t border-neutral-100 dark:border-neutral-700/50">
      <label className="flex items-center justify-between gap-2 cursor-pointer">
        <span className="text-xs text-neutral-600 dark:text-neutral-300">
          Inbound bot control
          <span className="block text-[10px] text-neutral-400">Let this chat create/manage tasks (/task, /board, /runner…). Needs a bot token above.</span>
        </span>
        <input type="checkbox" checked={enabled} onChange={toggle} disabled={!loaded} className="rounded" />
      </label>
    </div>
  );
}
