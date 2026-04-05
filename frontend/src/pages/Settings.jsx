import { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Server,
  Database,
  Terminal,
  Info,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  ExternalLink,
  Globe,
  Mail,
  Clock,
  Save,
  Moon,
  Sun,
  FolderOpen,
  Bell,
} from '../components/icons';
import apiClient from '../services/api';
import workspaceService from '../services/workspaceService';
import notificationService from '../services/notificationService';
import { useTheme } from '../contexts/ThemeContext';

const Settings = () => {
  const { theme, toggleTheme, isDark, primaryColor, setPrimaryColor, colorThemes } = useTheme();
  const [activeTab, setActiveTab] = useState('general');
  const [systemStatus, setSystemStatus] = useState({
    backend: { status: 'checking', latency: 0, version: '' },
    database: { status: 'checking', connected: false, version: '' },
    exegol: { status: 'checking', running: false, container: '' }
  });
  const [systemInfo, setSystemInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [commandTimeout, setCommandTimeout] = useState(300);
  const [originalTimeout, setOriginalTimeout] = useState(300);
  const [savingTimeout, setSavingTimeout] = useState(false);
  const [timeoutMessage, setTimeoutMessage] = useState(null);
  const [approvalTimeout, setApprovalTimeout] = useState(30);
  const [originalApprovalTimeout, setOriginalApprovalTimeout] = useState(30);
  const [savingApprovalTimeout, setSavingApprovalTimeout] = useState(false);
  const [approvalTimeoutMessage, setApprovalTimeoutMessage] = useState(null);
  const [containerName, setContainerName] = useState('');
  const [originalContainerName, setOriginalContainerName] = useState('');
  const [savingContainer, setSavingContainer] = useState(false);
  const [containerMessage, setContainerMessage] = useState(null);
  const [availableContainers, setAvailableContainers] = useState([]);
  const [loadingContainers, setLoadingContainers] = useState(false);
  const [outputMaxLength, setOutputMaxLength] = useState(5000);
  const [originalOutputMaxLength, setOriginalOutputMaxLength] = useState(5000);
  const [savingOutputMaxLength, setSavingOutputMaxLength] = useState(false);
  const [outputMaxLengthMessage, setOutputMaxLengthMessage] = useState(null);
  const [pythonExecOutputMaxLength, setPythonExecOutputMaxLength] = useState(5000);
  const [originalPythonExecOutputMaxLength, setOriginalPythonExecOutputMaxLength] = useState(5000);
  const [savingPythonExecOutputMaxLength, setSavingPythonExecOutputMaxLength] = useState(false);
  const [pythonExecOutputMaxLengthMessage, setPythonExecOutputMaxLengthMessage] = useState(null);
  const [httpRequestOutputMaxLength, setHttpRequestOutputMaxLength] = useState(5000);
  const [originalHttpRequestOutputMaxLength, setOriginalHttpRequestOutputMaxLength] = useState(5000);
  const [savingHttpRequestOutputMaxLength, setSavingHttpRequestOutputMaxLength] = useState(false);
  const [httpRequestOutputMaxLengthMessage, setHttpRequestOutputMaxLengthMessage] = useState(null);
  const [commandHistoryLimit, setCommandHistoryLimit] = useState(10);
  const [originalHistoryLimit, setOriginalHistoryLimit] = useState(10);
  const [savingHistoryLimit, setSavingHistoryLimit] = useState(false);
  const [historyLimitMessage, setHistoryLimitMessage] = useState(null);
  const [openingWorkspace, setOpeningWorkspace] = useState(false);
  const [workspaceMessage, setWorkspaceMessage] = useState(null);
  // Upload limits
  const [contextFileSizeMB, setContextFileSizeMB] = useState(200);
  const [origContextFileSizeMB, setOrigContextFileSizeMB] = useState(200);
  const [sourceZipSizeMB, setSourceZipSizeMB] = useState(200);
  const [origSourceZipSizeMB, setOrigSourceZipSizeMB] = useState(200);
  const [savingUploadLimits, setSavingUploadLimits] = useState(false);
  const [uploadLimitsMessage, setUploadLimitsMessage] = useState(null);


  useEffect(() => {
    loadSystemStatus();
    loadSystemInfo();
    loadCommandTimeout();
    loadApprovalTimeout();
    loadOutputMaxLength();
    loadPythonExecOutputMaxLength();
    loadHttpRequestOutputMaxLength();
    loadCommandHistoryLimit();
    loadExegolContainers();
    loadUploadLimits();
  }, []);


  const loadSystemStatus = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get('/system/status');
      setSystemStatus(data);
    } catch (error) {
      // console.error('Failed to load system status:', error);
      setSystemStatus({
        backend: { status: 'error', latency: 0, version: '' },
        database: { status: 'error', connected: false, version: '' },
        exegol: { status: 'error', running: false, container: '' }
      });
    } finally {
      setLoading(false);
    }
  };

  const loadSystemInfo = async () => {
    try {
      const { data } = await apiClient.get('/system/info');
      setSystemInfo(data);
      if (data.container_name) {
        setContainerName(data.container_name);
        setOriginalContainerName(data.container_name);
      }
    } catch (error) {
      // console.error('Failed to load system info:', error);
    }
  };

  const loadCommandTimeout = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/command_timeout');
      const timeoutValue = parseInt(data.value);
      setCommandTimeout(timeoutValue);
      setOriginalTimeout(timeoutValue);
    } catch (error) {
      // console.error('Failed to load command timeout:', error);
      // Use default value if loading fails
      setCommandTimeout(300);
      setOriginalTimeout(300);
    }
  };

  const loadOutputMaxLength = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/output_max_length');
      const maxLengthValue = parseInt(data.value);
      setOutputMaxLength(maxLengthValue);
      setOriginalOutputMaxLength(maxLengthValue);
    } catch (error) {
      // console.error('Failed to load output max length:', error);
      // Use default value if loading fails
      setOutputMaxLength(5000);
      setOriginalOutputMaxLength(5000);
    }
  };

  const loadExegolContainers = async () => {
    setLoadingContainers(true);
    try {
      const { data } = await apiClient.get('/system/exegol/containers');
      setAvailableContainers(data.containers || []);
    } catch (error) {
      // console.error('Failed to load Exegol containers:', error);
      setAvailableContainers([]);
    } finally {
      setLoadingContainers(false);
    }
  };

  const handleSaveTimeout = async () => {
    // Validate timeout value
    if (commandTimeout < 30 || commandTimeout > 1800) {
      setTimeoutMessage({ type: 'error', text: 'Timeout must be between 30 and 1800 seconds (30s to 30min)' });
      setTimeout(() => setTimeoutMessage(null), 5000);
      return;
    }

    setSavingTimeout(true);
    setTimeoutMessage(null);

    try {
      await apiClient.put('/system/settings/command_timeout', {
        value: commandTimeout.toString()
      });

      setOriginalTimeout(commandTimeout);
      setTimeoutMessage({ type: 'success', text: 'Command timeout updated successfully' });
      setTimeout(() => setTimeoutMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save command timeout:', error);
      setTimeoutMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save timeout setting' });
      setTimeout(() => setTimeoutMessage(null), 5000);
    } finally {
      setSavingTimeout(false);
    }
  };

  const handleTimeoutPreset = (seconds) => {
    setCommandTimeout(seconds);
  };

  const loadApprovalTimeout = async () => {
    try {
      const { data } = await apiClient.get('/command-settings');
      const timeoutValue = data.timeout_seconds || 30;
      setApprovalTimeout(timeoutValue);
      setOriginalApprovalTimeout(timeoutValue);
    } catch (error) {
      // console.error('Failed to load approval timeout:', error);
      setApprovalTimeout(30);
      setOriginalApprovalTimeout(30);
    }
  };

  const handleSaveApprovalTimeout = async () => {
    if (approvalTimeout < 10 || approvalTimeout > 600) {
      setApprovalTimeoutMessage({ type: 'error', text: 'Timeout must be between 10 and 600 seconds (10s to 10min)' });
      setTimeout(() => setApprovalTimeoutMessage(null), 5000);
      return;
    }

    setSavingApprovalTimeout(true);
    setApprovalTimeoutMessage(null);

    try {
      await apiClient.put('/command-settings', { timeout_seconds: approvalTimeout });

      setOriginalApprovalTimeout(approvalTimeout);
      setApprovalTimeoutMessage({ type: 'success', text: 'Approval timeout updated successfully' });
      setTimeout(() => setApprovalTimeoutMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save approval timeout:', error);
      setApprovalTimeoutMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save approval timeout' });
      setTimeout(() => setApprovalTimeoutMessage(null), 5000);
    } finally {
      setSavingApprovalTimeout(false);
    }
  };

  const handleApprovalTimeoutPreset = (seconds) => {
    setApprovalTimeout(seconds);
  };

  const handleSaveOutputMaxLength = async () => {
    // Validate output max length value
    if (outputMaxLength !== -1 && (outputMaxLength < 500 || outputMaxLength > 100000)) {
      setOutputMaxLengthMessage({ type: 'error', text: 'Output max length must be between 500 and 100000 characters, or -1 for unlimited' });
      setTimeout(() => setOutputMaxLengthMessage(null), 5000);
      return;
    }

    setSavingOutputMaxLength(true);
    setOutputMaxLengthMessage(null);

    try {
      await apiClient.put('/system/settings/output_max_length', {
        value: outputMaxLength.toString()
      });

      setOriginalOutputMaxLength(outputMaxLength);
      setOutputMaxLengthMessage({ type: 'success', text: 'Output max length updated successfully' });
      setTimeout(() => setOutputMaxLengthMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save output max length:', error);
      setOutputMaxLengthMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save output max length setting' });
      setTimeout(() => setOutputMaxLengthMessage(null), 5000);
    } finally {
      setSavingOutputMaxLength(false);
    }
  };

  const handleOutputMaxLengthPreset = (value) => {
    setOutputMaxLength(value);
  };

  const loadPythonExecOutputMaxLength = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/python_exec_output_max_length');
      const val = parseInt(data.value);
      setPythonExecOutputMaxLength(val);
      setOriginalPythonExecOutputMaxLength(val);
    } catch {
      setPythonExecOutputMaxLength(5000);
      setOriginalPythonExecOutputMaxLength(5000);
    }
  };

  const handleSavePythonExecOutputMaxLength = async () => {
    if (pythonExecOutputMaxLength !== -1 && (pythonExecOutputMaxLength < 500 || pythonExecOutputMaxLength > 100000)) {
      setPythonExecOutputMaxLengthMessage({ type: 'error', text: 'Must be between 500 and 100000 characters, or -1 for unlimited' });
      setTimeout(() => setPythonExecOutputMaxLengthMessage(null), 5000);
      return;
    }
    setSavingPythonExecOutputMaxLength(true);
    setPythonExecOutputMaxLengthMessage(null);
    try {
      await apiClient.put('/system/settings/python_exec_output_max_length', { value: pythonExecOutputMaxLength.toString() });
      setOriginalPythonExecOutputMaxLength(pythonExecOutputMaxLength);
      setPythonExecOutputMaxLengthMessage({ type: 'success', text: 'python_exec output limit updated' });
      setTimeout(() => setPythonExecOutputMaxLengthMessage(null), 3000);
    } catch (error) {
      setPythonExecOutputMaxLengthMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save' });
      setTimeout(() => setPythonExecOutputMaxLengthMessage(null), 5000);
    } finally {
      setSavingPythonExecOutputMaxLength(false);
    }
  };

  const handlePythonExecOutputMaxLengthPreset = (value) => {
    setPythonExecOutputMaxLength(value);
  };

  const loadHttpRequestOutputMaxLength = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/http_request_output_max_length');
      const val = parseInt(data.value);
      setHttpRequestOutputMaxLength(val);
      setOriginalHttpRequestOutputMaxLength(val);
    } catch {
      setHttpRequestOutputMaxLength(5000);
      setOriginalHttpRequestOutputMaxLength(5000);
    }
  };

  const handleSaveHttpRequestOutputMaxLength = async () => {
    if (httpRequestOutputMaxLength !== -1 && (httpRequestOutputMaxLength < 500 || httpRequestOutputMaxLength > 100000)) {
      setHttpRequestOutputMaxLengthMessage({ type: 'error', text: 'Must be between 500 and 100000 characters, or -1 for unlimited' });
      setTimeout(() => setHttpRequestOutputMaxLengthMessage(null), 5000);
      return;
    }
    setSavingHttpRequestOutputMaxLength(true);
    setHttpRequestOutputMaxLengthMessage(null);
    try {
      await apiClient.put('/system/settings/http_request_output_max_length', { value: httpRequestOutputMaxLength.toString() });
      setOriginalHttpRequestOutputMaxLength(httpRequestOutputMaxLength);
      setHttpRequestOutputMaxLengthMessage({ type: 'success', text: 'http_request output limit updated' });
      setTimeout(() => setHttpRequestOutputMaxLengthMessage(null), 3000);
    } catch (error) {
      setHttpRequestOutputMaxLengthMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save' });
      setTimeout(() => setHttpRequestOutputMaxLengthMessage(null), 5000);
    } finally {
      setSavingHttpRequestOutputMaxLength(false);
    }
  };

  const handleHttpRequestOutputMaxLengthPreset = (value) => {
    setHttpRequestOutputMaxLength(value);
  };

  const loadCommandHistoryLimit = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/command_history_limit');
      const limitValue = parseInt(data.value);
      setCommandHistoryLimit(limitValue);
      setOriginalHistoryLimit(limitValue);
    } catch (error) {
      console.error('Failed to load command history limit:', error);
      // Use default value if loading fails
      setCommandHistoryLimit(10);
      setOriginalHistoryLimit(10);
    }
  };

  const handleSaveCommandHistoryLimit = async () => {
    // Validate history limit value
    if (commandHistoryLimit < 0 || commandHistoryLimit > 100) {
      setHistoryLimitMessage({ type: 'error', text: 'Command history limit must be between 0 and 100' });
      setTimeout(() => setHistoryLimitMessage(null), 5000);
      return;
    }

    setSavingHistoryLimit(true);
    setHistoryLimitMessage(null);

    try {
      await apiClient.put('/system/settings/command_history_limit', {
        value: commandHistoryLimit.toString()
      });

      setOriginalHistoryLimit(commandHistoryLimit);
      setHistoryLimitMessage({ type: 'success', text: 'Command history limit updated successfully' });
      setTimeout(() => setHistoryLimitMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save command history limit:', error);
      setHistoryLimitMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save command history limit setting' });
      setTimeout(() => setHistoryLimitMessage(null), 5000);
    } finally {
      setSavingHistoryLimit(false);
    }
  };

  const handleHistoryLimitPreset = (value) => {
    setCommandHistoryLimit(value);
  };

  const loadUploadLimits = async () => {
    try {
      const [{ data: ctx }, { data: zip }] = await Promise.all([
        apiClient.get('/system/settings/max_context_file_size'),
        apiClient.get('/system/settings/max_source_zip_size'),
      ]);
      const ctxMB = parseInt(ctx.value) || 200;
      const zipMB = parseInt(zip.value) || 200;
      setContextFileSizeMB(ctxMB);
      setOrigContextFileSizeMB(ctxMB);
      setSourceZipSizeMB(zipMB);
      setOrigSourceZipSizeMB(zipMB);
    } catch {
      // Use defaults already set in state
    }
  };

  const handleSaveUploadLimits = async () => {
    if (contextFileSizeMB < 1 || contextFileSizeMB > 2000 || sourceZipSizeMB < 1 || sourceZipSizeMB > 2000) {
      setUploadLimitsMessage({ type: 'error', text: 'Values must be between 1 and 2000 MB' });
      setTimeout(() => setUploadLimitsMessage(null), 5000);
      return;
    }
    setSavingUploadLimits(true);
    setUploadLimitsMessage(null);
    try {
      await Promise.all([
        apiClient.put('/system/settings/max_context_file_size', { value: contextFileSizeMB.toString() }),
        apiClient.put('/system/settings/max_source_zip_size', { value: sourceZipSizeMB.toString() }),
      ]);
      setOrigContextFileSizeMB(contextFileSizeMB);
      setOrigSourceZipSizeMB(sourceZipSizeMB);
      setUploadLimitsMessage({ type: 'success', text: 'Upload limits saved' });
      setTimeout(() => setUploadLimitsMessage(null), 3000);
    } catch (error) {
      setUploadLimitsMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save upload limits' });
      setTimeout(() => setUploadLimitsMessage(null), 5000);
    } finally {
      setSavingUploadLimits(false);
    }
  };


  const handleOpenWorkspace = async () => {
    setOpeningWorkspace(true);
    setWorkspaceMessage(null);

    try {
      const result = await workspaceService.openRootWorkspace();

      if (result.success && result.host_path) {
        // Try to open via local folder opener service (runs on host)
        try {
          const { openFolderOnHost } = await import('../services/folderOpenerService');
          const openResult = await openFolderOnHost(result.host_path);
          if (openResult.success) {
            setWorkspaceMessage({
              type: 'success',
              text: `Opened in ${openResult.os} file explorer`
            });
            setTimeout(() => setWorkspaceMessage(null), 3000);
            return;
          }
        } catch (serviceError) {
          console.log('Folder opener service not available:', serviceError.message);
        }

        // Fallback: Copy path to clipboard
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(result.host_path);
          setWorkspaceMessage({
            type: 'success',
            text: `Path copied: ${result.host_path}`
          });
        } else {
          setWorkspaceMessage({
            type: 'success',
            text: result.host_path
          });
        }
        setTimeout(() => setWorkspaceMessage(null), 5000);
      }
    } catch (error) {
      console.error('Failed to open workspace:', error);
      setWorkspaceMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Failed to get workspace path'
      });
      setTimeout(() => setWorkspaceMessage(null), 5000);
    } finally {
      setOpeningWorkspace(false);
    }
  };

  const formatOutputLength = (length) => {
    if (length === -1) return 'Unlimited';
    if (length < 1000) return `${length} chars`;
    return `${(length / 1000).toFixed(1)}K chars`;
  };

  const handleSaveContainer = async () => {
    if (!containerName || containerName.trim() === '') {
      setContainerMessage({ type: 'error', text: 'Container name cannot be empty' });
      setTimeout(() => setContainerMessage(null), 5000);
      return;
    }

    setSavingContainer(true);
    setContainerMessage(null);

    try {
      await apiClient.put('/system/settings/container_name', {
        value: containerName.trim()
      });

      setOriginalContainerName(containerName.trim());
      setContainerMessage({ type: 'success', text: 'Container name updated successfully' });
      setTimeout(() => setContainerMessage(null), 3000);

      // Reload system info and status
      await loadSystemInfo();
      await loadSystemStatus();
    } catch (error) {
      console.error('Failed to save container name:', error);
      setContainerMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save container name' });
      setTimeout(() => setContainerMessage(null), 5000);
    } finally {
      setSavingContainer(false);
    }
  };

  const formatTime = (seconds) => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  };

  // Notifications state
  const [notifConfigs, setNotifConfigs] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [notifTesting, setNotifTesting] = useState('');
  const [notifMessage, setNotifMessage] = useState(null);
  // Telegram
  const [tgEnabled, setTgEnabled] = useState(false);
  const [tgBotToken, setTgBotToken] = useState('');
  const [tgChatId, setTgChatId] = useState('');
  const [tgOnCritical, setTgOnCritical] = useState(true);
  const [tgOnHigh, setTgOnHigh] = useState(true);
  const [tgOnScan, setTgOnScan] = useState(false);
  // Slack
  const [slackEnabled, setSlackEnabled] = useState(false);
  const [slackWebhook, setSlackWebhook] = useState('');
  const [slackOnCritical, setSlackOnCritical] = useState(true);
  const [slackOnHigh, setSlackOnHigh] = useState(true);
  const [slackOnScan, setSlackOnScan] = useState(false);
  // Email
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [emailSmtpHost, setEmailSmtpHost] = useState('');
  const [emailSmtpPort, setEmailSmtpPort] = useState(587);
  const [emailUsername, setEmailUsername] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [emailFrom, setEmailFrom] = useState('');
  const [emailTo, setEmailTo] = useState('');
  const [emailEncryption, setEmailEncryption] = useState('starttls'); // none, starttls, ssl
  const [emailSubject, setEmailSubject] = useState('AIDA Security Alert');
  const [emailOnCritical, setEmailOnCritical] = useState(true);
  const [emailOnHigh, setEmailOnHigh] = useState(true);
  const [emailOnScan, setEmailOnScan] = useState(false);

  useEffect(() => {
    if (activeTab === 'notifications') loadNotifConfigs();
  }, [activeTab]);

  const loadNotifConfigs = async () => {
    setNotifLoading(true);
    try {
      const configs = await notificationService.listConfigs();
      setNotifConfigs(configs);
      configs.forEach(cfg => {
        if (cfg.channel === 'telegram') {
          setTgEnabled(cfg.enabled);
          setTgBotToken(cfg.config?.bot_token || '');
          setTgChatId(cfg.config?.chat_id || '');
          setTgOnCritical(cfg.on_critical_finding);
          setTgOnHigh(cfg.on_high_finding);
          setTgOnScan(cfg.on_scan_complete);
        } else if (cfg.channel === 'slack') {
          setSlackEnabled(cfg.enabled);
          setSlackWebhook(cfg.config?.webhook_url || '');
          setSlackOnCritical(cfg.on_critical_finding);
          setSlackOnHigh(cfg.on_high_finding);
          setSlackOnScan(cfg.on_scan_complete);
        } else if (cfg.channel === 'email') {
          setEmailEnabled(cfg.enabled);
          setEmailSmtpHost(cfg.config?.smtp_host || '');
          setEmailSmtpPort(cfg.config?.smtp_port || 587);
          setEmailUsername(cfg.config?.username || '');
          setEmailPassword(cfg.config?.password || '');
          setEmailFrom(cfg.config?.from_email || '');
          setEmailTo((cfg.config?.to_emails || []).join(', '));
          setEmailEncryption(cfg.config?.encryption || 'starttls');
          setEmailSubject(cfg.config?.subject || 'AIDA Security Alert');
          setEmailOnCritical(cfg.on_critical_finding);
          setEmailOnHigh(cfg.on_high_finding);
          setEmailOnScan(cfg.on_scan_complete);
        }
      });
    } catch (e) {
      // ignore
    } finally {
      setNotifLoading(false);
    }
  };

  const saveNotifChannel = async (channel) => {
    setNotifMessage(null);
    try {
      let body = {};
      if (channel === 'telegram') {
        body = {
          enabled: tgEnabled,
          config: { bot_token: tgBotToken, chat_id: tgChatId },
          on_critical_finding: tgOnCritical,
          on_high_finding: tgOnHigh,
          on_scan_complete: tgOnScan,
        };
      } else if (channel === 'slack') {
        body = {
          enabled: slackEnabled,
          config: { webhook_url: slackWebhook },
          on_critical_finding: slackOnCritical,
          on_high_finding: slackOnHigh,
          on_scan_complete: slackOnScan,
        };
      } else if (channel === 'email') {
        body = {
          enabled: emailEnabled,
          config: {
            smtp_host: emailSmtpHost,
            smtp_port: emailSmtpPort,
            username: emailUsername,
            password: emailPassword,
            from_email: emailFrom,
            to_emails: emailTo.split(',').map(s => s.trim()).filter(Boolean),
            encryption: emailEncryption,
            subject: emailSubject,
          },
          on_critical_finding: emailOnCritical,
          on_high_finding: emailOnHigh,
          on_scan_complete: emailOnScan,
        };
      }
      await notificationService.updateConfig(channel, body);
      setNotifMessage({ type: 'success', text: `${channel} configuration saved` });
      setTimeout(() => setNotifMessage(null), 3000);
    } catch (e) {
      setNotifMessage({ type: 'error', text: e.response?.data?.detail || 'Failed to save' });
      setTimeout(() => setNotifMessage(null), 5000);
    }
  };

  const testNotifChannel = async (channel) => {
    setNotifTesting(channel);
    try {
      const res = await notificationService.testChannel(channel);
      setNotifMessage({ type: res.success ? 'success' : 'error', text: res.message });
      setTimeout(() => setNotifMessage(null), 5000);
    } catch (e) {
      setNotifMessage({ type: 'error', text: e.response?.data?.detail || 'Test failed' });
      setTimeout(() => setNotifMessage(null), 5000);
    } finally {
      setNotifTesting('');
    }
  };

  const tabs = [
    { id: 'general', label: 'General', icon: SettingsIcon },
    { id: 'tools', label: 'Tools', icon: Terminal },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'about', label: 'About', icon: Info }
  ];

  return (
    <div className="space-y-6 animate-in">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Settings</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          System status and configuration
        </p>
      </div>

      {/* Horizontal Tabs Navigation */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="flex gap-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 pb-3 border-b-2 transition-colors ${activeTab === tab.id
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200'
                  }`}
              >
                <Icon className="w-4 h-4" />
                <span className="font-medium text-sm">{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Content Area */}
      <div className="pb-12">
        {/* TAB 1: GENERAL */}
        {activeTab === 'general' && (
          <div className="space-y-6">
            {/* Appearance Settings */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Appearance</h2>

              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700">
                {/* Theme Toggle */}
                <div className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {isDark ? (
                      <Moon className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    ) : (
                      <Sun className="w-4 h-4 text-neutral-500" />
                    )}
                    <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Theme</span>
                  </div>
                  <button
                    onClick={toggleTheme}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 ${isDark ? 'bg-primary-600' : 'bg-neutral-300'
                      }`}
                    role="switch"
                    aria-checked={isDark}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${isDark ? 'translate-x-6' : 'translate-x-1'
                        }`}
                    />
                  </button>
                </div>

                {/* Primary Color */}
                <div className="p-4">
                  <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-3">Primary Color</div>
                  <div className="grid grid-cols-4 gap-2">
                    {Object.entries(colorThemes).map(([key, colorTheme]) => {
                      const isActive = primaryColor === key;
                      return (
                        <button
                          key={key}
                          onClick={() => setPrimaryColor(key)}
                          className={`flex items-center gap-2 p-2 rounded border transition-colors ${isActive
                            ? 'border-primary-500 bg-primary-100/50 dark:bg-primary-900/20'
                            : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600 bg-white dark:bg-neutral-800'
                            }`}
                          title={colorTheme.name}
                        >
                          <div
                            className="w-5 h-5 rounded-full"
                            style={{ backgroundColor: colorTheme.colors[500] }}
                          />
                          <span className="text-xs font-medium text-neutral-900 dark:text-neutral-100">{colorTheme.name}</span>
                          {isActive && <CheckCircle className="w-3 h-3 text-primary-600 dark:text-primary-400 ml-auto" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Command Settings */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Command Settings</h2>

              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                  <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Command Timeout</span>
                </div>

                {/* Preset Buttons */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {[
                    { label: '3m', value: 180 },
                    { label: '5m', value: 300 },
                    { label: '10m', value: 600 },
                    { label: '15m', value: 900 },
                    { label: '30m', value: 1800 }
                  ].map((preset) => (
                    <button
                      key={preset.value}
                      onClick={() => handleTimeoutPreset(preset.value)}
                      className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${commandTimeout === preset.value
                        ? 'bg-primary-600 text-white border-primary-600'
                        : 'bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500'
                        }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                {/* Custom Input */}
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="30"
                    max="1800"
                    value={commandTimeout}
                    onChange={(e) => setCommandTimeout(parseInt(e.target.value) || 30)}
                    className="w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <span className="text-xs text-neutral-600 dark:text-neutral-400">seconds ({formatTime(commandTimeout)})</span>
                  <button
                    onClick={handleSaveTimeout}
                    disabled={savingTimeout || commandTimeout === originalTimeout}
                    className="ml-auto px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    {savingTimeout ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Saving
                      </>
                    ) : (
                      <>
                        <Save className="w-3 h-3" />
                        Save
                      </>
                    )}
                  </button>
                </div>

                {/* Success/Error Message */}
                {timeoutMessage && (
                  <div className={`mt-2 p-2 rounded text-xs flex items-center gap-1.5 ${timeoutMessage.type === 'success'
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                    {timeoutMessage.type === 'success' ? (
                      <CheckCircle className="w-3 h-3 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3 h-3 flex-shrink-0" />
                    )}
                    <span>{timeoutMessage.text}</span>
                  </div>
                )}
              </div>

              {/* Approval Timeout Setting */}
              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 mt-4">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                  <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Approval Timeout</span>
                  <span className="text-xs text-neutral-500">(Command Approval)</span>
                </div>

                {/* Preset Buttons */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {[
                    { label: '15s', value: 15 },
                    { label: '30s', value: 30 },
                    { label: '1m', value: 60 },
                    { label: '2m', value: 120 },
                    { label: '5m', value: 300 }
                  ].map((preset) => (
                    <button
                      key={preset.value}
                      onClick={() => handleApprovalTimeoutPreset(preset.value)}
                      className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${approvalTimeout === preset.value
                        ? 'bg-primary-600 text-white border-primary-600'
                        : 'bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500'
                        }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                {/* Custom Input */}
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="10"
                    max="600"
                    value={approvalTimeout}
                    onChange={(e) => setApprovalTimeout(parseInt(e.target.value) || 30)}
                    className="w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <span className="text-xs text-neutral-600 dark:text-neutral-400">seconds ({formatTime(approvalTimeout)})</span>
                  <button
                    onClick={handleSaveApprovalTimeout}
                    disabled={savingApprovalTimeout || approvalTimeout === originalApprovalTimeout}
                    className="ml-auto px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    {savingApprovalTimeout ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Saving
                      </>
                    ) : (
                      <>
                        <Save className="w-3 h-3" />
                        Save
                      </>
                    )}
                  </button>
                </div>

                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
                  Time to wait for user approval before rejecting a blocked command.
                </p>

                {/* Success/Error Message */}
                {approvalTimeoutMessage && (
                  <div className={`mt-2 p-2 rounded text-xs flex items-center gap-1.5 ${approvalTimeoutMessage.type === 'success'
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                    {approvalTimeoutMessage.type === 'success' ? (
                      <CheckCircle className="w-3 h-3 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3 h-3 flex-shrink-0" />
                    )}
                    <span>{approvalTimeoutMessage.text}</span>
                  </div>
                )}
              </div>

              {/* Command History Limit Setting */}
              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 mt-4">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                  <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Command History Limit</span>
                </div>

                {/* Preset Buttons */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {[5, 10, 20, 50, 100].map((preset) => (
                    <button
                      key={preset}
                      onClick={() => handleHistoryLimitPreset(preset)}
                      className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${commandHistoryLimit === preset
                        ? 'bg-primary-600 text-white border-primary-600'
                        : 'bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500'
                        }`}
                    >
                      {preset}
                    </button>
                  ))}
                </div>

                {/* Custom Input */}
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={commandHistoryLimit}
                    onChange={(e) => setCommandHistoryLimit(Math.min(100, Math.max(0, parseInt(e.target.value) || 0)))}
                    className="w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <span className="text-xs text-neutral-600 dark:text-neutral-400">commands</span>
                  <button
                    onClick={handleSaveCommandHistoryLimit}
                    disabled={savingHistoryLimit || commandHistoryLimit === originalHistoryLimit}
                    className="ml-auto px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    {savingHistoryLimit ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Saving
                      </>
                    ) : (
                      <>
                        <Save className="w-3 h-3" />
                        Save
                      </>
                    )}
                  </button>
                </div>

                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
                  Number of recent commands to include when loading an assessment via MCP.
                </p>

                {/* Success/Error Message */}
                {historyLimitMessage && (
                  <div className={`mt-2 p-2 rounded text-xs flex items-center gap-1.5 ${historyLimitMessage.type === 'success'
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                    {historyLimitMessage.type === 'success' ? (
                      <CheckCircle className="w-3 h-3 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3 h-3 flex-shrink-0" />
                    )}
                    <span>{historyLimitMessage.text}</span>
                  </div>
                )}
              </div>

              {/* Output Max Length — grouped */}
              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 mt-4">
                <div className="flex items-center gap-2 mb-1">
                  <Terminal className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                  <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Output Max Length</span>
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
                  Controls how much output is shown to the AI before truncation. Use -1 for unlimited. Configured per tool.
                </p>

                {(() => {
                  const OUTPUT_PRESETS = [
                    { label: '1K', value: 1000 },
                    { label: '2.5K', value: 2500 },
                    { label: '5K', value: 5000 },
                    { label: '10K', value: 10000 },
                    { label: '50K', value: 50000 },
                    { label: '∞', value: -1 }
                  ];

                  const rows = [
                    {
                      key: 'execute',
                      label: 'execute',
                      value: outputMaxLength,
                      original: originalOutputMaxLength,
                      saving: savingOutputMaxLength,
                      message: outputMaxLengthMessage,
                      setValue: setOutputMaxLength,
                      onSave: handleSaveOutputMaxLength,
                    },
                    {
                      key: 'python_exec',
                      label: 'python_exec',
                      value: pythonExecOutputMaxLength,
                      original: originalPythonExecOutputMaxLength,
                      saving: savingPythonExecOutputMaxLength,
                      message: pythonExecOutputMaxLengthMessage,
                      setValue: setPythonExecOutputMaxLength,
                      onSave: handleSavePythonExecOutputMaxLength,
                    },
                    {
                      key: 'http_request',
                      label: 'http_request',
                      value: httpRequestOutputMaxLength,
                      original: originalHttpRequestOutputMaxLength,
                      saving: savingHttpRequestOutputMaxLength,
                      message: httpRequestOutputMaxLengthMessage,
                      setValue: setHttpRequestOutputMaxLength,
                      onSave: handleSaveHttpRequestOutputMaxLength,
                    },
                  ];

                  return (
                    <div className="divide-y divide-neutral-100 dark:divide-neutral-700">
                      {rows.map((row, idx) => (
                        <div key={row.key} className={`${idx > 0 ? 'pt-3' : ''} ${idx < rows.length - 1 ? 'pb-3' : ''}`}>
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 px-1.5 py-0.5 rounded w-28 shrink-0 truncate">
                              {row.label}
                            </code>
                            {OUTPUT_PRESETS.map((p) => (
                              <button
                                key={p.value}
                                onClick={() => row.setValue(p.value)}
                                className={`px-2 py-0.5 text-xs font-medium rounded border transition-colors ${row.value === p.value
                                  ? 'bg-primary-600 text-white border-primary-600'
                                  : 'bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500'
                                  }`}
                              >
                                {p.label}
                              </button>
                            ))}
                            <input
                              type="number"
                              min="-1"
                              max="100000"
                              value={row.value}
                              onChange={(e) => row.setValue(parseInt(e.target.value) || 500)}
                              className="w-24 px-2 py-1 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-xs focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                            />
                            <span className="text-xs text-neutral-500 dark:text-neutral-400 hidden sm:inline">
                              {formatOutputLength(row.value)}
                            </span>
                            <button
                              onClick={row.onSave}
                              disabled={row.saving || row.value === row.original}
                              className="ml-auto px-3 py-1 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                            >
                              {row.saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                              {row.saving ? 'Saving' : 'Save'}
                            </button>
                          </div>
                          {row.message && (
                            <div className={`mt-1.5 p-1.5 rounded text-xs flex items-center gap-1.5 ${row.message.type === 'success'
                              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                              }`}>
                              {row.message.type === 'success'
                                ? <CheckCircle className="w-3 h-3 flex-shrink-0" />
                                : <AlertCircle className="w-3 h-3 flex-shrink-0" />}
                              <span>{row.message.text}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Output Max Length warning */}
              {[outputMaxLength, pythonExecOutputMaxLength, httpRequestOutputMaxLength].some(v => v > 5000 && v !== -1) && (
                <div className="mt-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-700 dark:text-amber-300">
                    <span className="font-semibold">High token consumption warning —</span> One or more tools have an output limit above 5K characters. Large outputs can consume enormous numbers of tokens per command and are not recommended for large or verbose applications.
                  </div>
                </div>
              )}
            </div>

            {/* Upload Limits */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Upload Limits</h2>
              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
                <div className="space-y-4">
                  {/* Context file size */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Context File Limit</span>
                      <span className="text-xs text-neutral-500">(/context uploads)</span>
                    </div>
                    <div className="flex flex-wrap gap-2 mb-2">
                      {[10, 50, 100, 200, 500].map((mb) => (
                        <button key={mb} onClick={() => setContextFileSizeMB(mb)}
                          className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${contextFileSizeMB === mb
                            ? 'bg-primary-600 text-white border-primary-600'
                            : 'bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400'
                            }`}>{mb}MB</button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <input type="number" min="1" max="2000" value={contextFileSizeMB}
                        onChange={(e) => setContextFileSizeMB(parseInt(e.target.value) || 1)}
                        className="w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
                      <span className="text-xs text-neutral-600 dark:text-neutral-400">MB</span>
                    </div>
                  </div>

                  {/* Source ZIP size */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Source ZIP Limit</span>
                      <span className="text-xs text-neutral-500">(git ZIPs auto-routed to /source)</span>
                    </div>
                    <div className="flex flex-wrap gap-2 mb-2">
                      {[100, 200, 500, 1000, 2000].map((mb) => (
                        <button key={mb} onClick={() => setSourceZipSizeMB(mb)}
                          className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${sourceZipSizeMB === mb
                            ? 'bg-primary-600 text-white border-primary-600'
                            : 'bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border-neutral-300 dark:border-neutral-600 hover:border-neutral-400'
                            }`}>{mb}MB</button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <input type="number" min="1" max="2000" value={sourceZipSizeMB}
                        onChange={(e) => setSourceZipSizeMB(parseInt(e.target.value) || 1)}
                        className="w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
                      <span className="text-xs text-neutral-600 dark:text-neutral-400">MB</span>
                    </div>
                  </div>

                  {/* Save */}
                  <div className="flex items-center justify-between pt-2 border-t border-neutral-200 dark:border-neutral-700">
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">Changes take effect immediately (no restart required).</p>
                    <button onClick={handleSaveUploadLimits}
                      disabled={savingUploadLimits || (contextFileSizeMB === origContextFileSizeMB && sourceZipSizeMB === origSourceZipSizeMB)}
                      className="px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1">
                      {savingUploadLimits ? <><RefreshCw className="w-3 h-3 animate-spin" />Saving</> : <><Save className="w-3 h-3" />Save</>}
                    </button>
                  </div>

                  {uploadLimitsMessage && (
                    <div className={`p-2 rounded text-xs flex items-center gap-1.5 ${uploadLimitsMessage.type === 'success'
                      ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                      : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                      }`}>
                      {uploadLimitsMessage.type === 'success' ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                      <span>{uploadLimitsMessage.text}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>


            {/* System Info */}
            {systemInfo && (
              <div className="bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
                <div className="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
                  <Info className="w-3 h-3" />
                  <span>{systemInfo.platform_name} v{systemInfo.version}</span>
                  <span>•</span>
                  <span>FastAPI {systemInfo.fastapi_version}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: TOOLS */}
        {activeTab === 'tools' && (
          <div className="space-y-6">
            {/* Open Workspace Folder */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                Workspace Access
              </h2>

              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <FolderOpen className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <div>
                      <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                        Open Workspace Folder
                      </div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                        Opens /workspace directory in file explorer
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleOpenWorkspace}
                    disabled={openingWorkspace}
                    className="px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    {openingWorkspace ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Opening
                      </>
                    ) : (
                      <>
                        <FolderOpen className="w-3 h-3" />
                        Open Folder
                      </>
                    )}
                  </button>
                </div>

                {workspaceMessage && (
                  <div className={`mt-2 p-2 rounded text-xs flex items-center gap-1.5 ${workspaceMessage.type === 'success'
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                    {workspaceMessage.type === 'success' ? (
                      <CheckCircle className="w-3 h-3 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3 h-3 flex-shrink-0" />
                    )}
                    <span>{workspaceMessage.text}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Exegol Configuration */}
            {systemInfo && (
              <div>
                <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Exegol Configuration</h2>

                <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
                  <div className="mb-3">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Terminal className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                        <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Container Selection</span>
                      </div>
                      <button
                        onClick={loadExegolContainers}
                        disabled={loadingContainers}
                        className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 flex items-center gap-1 disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3 h-3 ${loadingContainers ? 'animate-spin' : ''}`} />
                        Detect
                      </button>
                    </div>

                    {loadingContainers ? (
                      <div className="flex items-center justify-center p-4 text-xs text-neutral-500 dark:text-neutral-400">
                        <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                        Detecting containers...
                      </div>
                    ) : availableContainers.length === 0 ? (
                      <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded text-xs text-yellow-700 dark:text-yellow-400">
                        <AlertCircle className="w-4 h-4 inline mr-2" />
                        No Exegol containers detected. Make sure Docker is running and you have Exegol containers.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {availableContainers.map((container) => (
                          <label
                            key={container.id}
                            className={`flex items-center justify-between p-3 border-2 rounded cursor-pointer transition-colors ${containerName === container.name
                              ? 'border-primary-500 bg-primary-100/50 dark:bg-primary-900/20'
                              : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600'
                              }`}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="radio"
                                name="container"
                                value={container.name}
                                checked={containerName === container.name}
                                onChange={(e) => setContainerName(e.target.value)}
                                className="w-4 h-4 text-primary-600 focus:ring-primary-500"
                              />
                              <div>
                                <div className="text-sm font-mono font-medium text-neutral-900 dark:text-neutral-100">
                                  {container.name}
                                </div>
                                <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                                  {container.image} • {container.id}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1">
                              {container.status === 'running' ? (
                                <>
                                  <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                                  <span className="text-xs text-green-700 dark:text-green-400">Running</span>
                                </>
                              ) : (
                                <>
                                  <div className="w-1.5 h-1.5 bg-neutral-400 rounded-full"></div>
                                  <span className="text-xs text-neutral-600 dark:text-neutral-400 capitalize">{container.status}</span>
                                </>
                              )}
                            </div>
                          </label>
                        ))}
                      </div>
                    )}

                    <div className="mt-3 flex items-center justify-end">
                      <button
                        onClick={handleSaveContainer}
                        disabled={savingContainer || containerName.trim() === originalContainerName || availableContainers.length === 0}
                        className="px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                      >
                        {savingContainer ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            Saving
                          </>
                        ) : (
                          <>
                            <Save className="w-3 h-3" />
                            Save Selection
                          </>
                        )}
                      </button>
                    </div>

                    <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
                      Default container for new assessments. Change per-assessment using the container badge.
                    </p>

                    {/* Success/Error Message */}
                    {containerMessage && (
                      <div className={`mt-2 p-2 rounded text-xs flex items-center gap-1.5 ${containerMessage.type === 'success'
                        ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                        : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                        }`}>
                        {containerMessage.type === 'success' ? (
                          <CheckCircle className="w-3 h-3 flex-shrink-0" />
                        ) : (
                          <AlertCircle className="w-3 h-3 flex-shrink-0" />
                        )}
                        <span>{containerMessage.text}</span>
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-neutral-200 dark:border-neutral-700">
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Workspace Path</div>
                    <code className="text-xs font-mono bg-neutral-100 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 px-2 py-1 rounded">
                      {systemInfo.workspace_base}
                    </code>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: NOTIFICATIONS */}
        {activeTab === 'notifications' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">Notification Channels</h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-4">Configure alerts for critical findings and scan completions</p>
            </div>

            {notifMessage && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${notifMessage.type === 'success' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'}`}>
                {notifMessage.type === 'success' ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                <span>{notifMessage.text}</span>
              </div>
            )}

            {/* Telegram */}
            <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">&#9993;</span>
                  <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Telegram</h3>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={tgEnabled} onChange={e => setTgEnabled(e.target.checked)} className="sr-only peer" />
                  <div className="w-9 h-5 bg-neutral-200 peer-focus:outline-none rounded-full peer dark:bg-neutral-700 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-600"></div>
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Bot Token</label>
                  <input type="password" value={tgBotToken} onChange={e => setTgBotToken(e.target.value)} placeholder="123456:ABC-DEF..." className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Chat ID</label>
                  <input type="text" value={tgChatId} onChange={e => setTgChatId(e.target.value)} placeholder="-100123456789" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={tgOnCritical} onChange={e => setTgOnCritical(e.target.checked)} className="rounded" /> Critical</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={tgOnHigh} onChange={e => setTgOnHigh(e.target.checked)} className="rounded" /> High</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={tgOnScan} onChange={e => setTgOnScan(e.target.checked)} className="rounded" /> Scan Complete</label>
              </div>
              <div className="flex gap-2">
                <button onClick={() => saveNotifChannel('telegram')} className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center gap-1"><Save className="w-3 h-3" /> Save</button>
                <button onClick={() => testNotifChannel('telegram')} disabled={notifTesting === 'telegram'} className="px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300 transition-colors disabled:opacity-50">
                  {notifTesting === 'telegram' ? 'Sending...' : 'Test'}
                </button>
              </div>
            </div>

            {/* Slack */}
            <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">#</span>
                  <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Slack</h3>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={slackEnabled} onChange={e => setSlackEnabled(e.target.checked)} className="sr-only peer" />
                  <div className="w-9 h-5 bg-neutral-200 peer-focus:outline-none rounded-full peer dark:bg-neutral-700 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-600"></div>
                </label>
              </div>
              <div>
                <label className="text-[10px] font-semibold text-neutral-500 uppercase">Webhook URL</label>
                <input type="url" value={slackWebhook} onChange={e => setSlackWebhook(e.target.value)} placeholder="https://hooks.slack.com/services/..." className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
              </div>
              <div className="flex items-center gap-4 text-xs">
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={slackOnCritical} onChange={e => setSlackOnCritical(e.target.checked)} className="rounded" /> Critical</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={slackOnHigh} onChange={e => setSlackOnHigh(e.target.checked)} className="rounded" /> High</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={slackOnScan} onChange={e => setSlackOnScan(e.target.checked)} className="rounded" /> Scan Complete</label>
              </div>
              <div className="flex gap-2">
                <button onClick={() => saveNotifChannel('slack')} className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center gap-1"><Save className="w-3 h-3" /> Save</button>
                <button onClick={() => testNotifChannel('slack')} disabled={notifTesting === 'slack'} className="px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300 transition-colors disabled:opacity-50">
                  {notifTesting === 'slack' ? 'Sending...' : 'Test'}
                </button>
              </div>
            </div>

            {/* Email */}
            <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Email (SMTP)</h3>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={emailEnabled} onChange={e => setEmailEnabled(e.target.checked)} className="sr-only peer" />
                  <div className="w-9 h-5 bg-neutral-200 peer-focus:outline-none rounded-full peer dark:bg-neutral-700 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-600"></div>
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">SMTP Host</label>
                  <input type="text" value={emailSmtpHost} onChange={e => setEmailSmtpHost(e.target.value)} placeholder="smtp.gmail.com" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">SMTP Port</label>
                  <input type="number" value={emailSmtpPort} onChange={e => setEmailSmtpPort(parseInt(e.target.value) || 587)} className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Username</label>
                  <input type="text" value={emailUsername} onChange={e => setEmailUsername(e.target.value)} placeholder="user@gmail.com" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Password</label>
                  <input type="password" value={emailPassword} onChange={e => setEmailPassword(e.target.value)} placeholder="App password" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">From Email</label>
                  <input type="email" value={emailFrom} onChange={e => setEmailFrom(e.target.value)} placeholder="aida@example.com" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">To Emails (comma-separated)</label>
                  <input type="text" value={emailTo} onChange={e => setEmailTo(e.target.value)} placeholder="admin@example.com, team@example.com" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Encryption</label>
                  <select value={emailEncryption} onChange={e => setEmailEncryption(e.target.value)} className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100">
                    <option value="none">None (plain)</option>
                    <option value="starttls">STARTTLS (port 587)</option>
                    <option value="ssl">SSL/TLS (port 465)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase">Subject</label>
                  <input type="text" value={emailSubject} onChange={e => setEmailSubject(e.target.value)} placeholder="AIDA Security Alert" className="mt-1 w-full text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100" />
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={emailOnCritical} onChange={e => setEmailOnCritical(e.target.checked)} className="rounded" /> Critical</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={emailOnHigh} onChange={e => setEmailOnHigh(e.target.checked)} className="rounded" /> High</label>
                <label className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={emailOnScan} onChange={e => setEmailOnScan(e.target.checked)} className="rounded" /> Scan Complete</label>
              </div>
              <div className="flex gap-2">
                <button onClick={() => saveNotifChannel('email')} className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center gap-1"><Save className="w-3 h-3" /> Save</button>
                <button onClick={() => testNotifChannel('email')} disabled={notifTesting === 'email'} className="px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300 transition-colors disabled:opacity-50">
                  {notifTesting === 'email' ? 'Sending...' : 'Test'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: ABOUT */}
        {activeTab === 'about' && (
          <div className="space-y-6">
            {/* System Information */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Platform Information</h2>

              {systemInfo ? (
                <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700">
                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Platform</span>
                    <span className="text-xs font-medium text-neutral-900 dark:text-neutral-100">{systemInfo.platform_name} v{systemInfo.version}</span>
                  </div>

                  {/* Backend Status */}
                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Backend API</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">FastAPI {systemInfo.fastapi_version}</span>
                      {systemStatus.backend.status === 'connected' ? (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                          <span className="text-xs font-medium text-green-700 dark:text-green-400">{systemStatus.backend.latency}ms</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-red-500 rounded-full"></div>
                          <span className="text-xs font-medium text-red-700 dark:text-red-400">Error</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Frontend Status */}
                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Frontend</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">React + Vite</span>
                      <div className="flex items-center gap-1">
                        <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                        <span className="text-xs font-medium text-green-700 dark:text-green-400">Active</span>
                      </div>
                    </div>
                  </div>

                  {/* Database Status */}
                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Database</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">PostgreSQL {systemStatus.database.version}</span>
                      {systemStatus.database.connected ? (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                          <span className="text-xs font-medium text-green-700 dark:text-green-400">Connected</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-red-500 rounded-full"></div>
                          <span className="text-xs font-medium text-red-700 dark:text-red-400">Disconnected</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Exegol Container Status */}
                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Exegol Container</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400 max-w-[120px] truncate">{systemStatus.exegol.container || systemInfo.container_name}</span>
                      {systemStatus.exegol.running ? (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                          <span className="text-xs font-medium text-green-700 dark:text-green-400">Running</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 bg-amber-500 rounded-full"></div>
                          <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Stopped</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Python Version</span>
                    <span className="text-xs font-medium text-neutral-900 dark:text-neutral-100">{systemInfo.python_version}</span>
                  </div>

                  <div className="p-3 flex items-center justify-between">
                    <span className="text-xs text-neutral-600 dark:text-neutral-400">Environment</span>
                    <span className="text-xs font-medium text-neutral-900 dark:text-neutral-100 capitalize">{systemInfo.environment}</span>
                  </div>
                </div>
              ) : (
                <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 text-center">
                  <AlertCircle className="w-8 h-8 mx-auto mb-2 text-neutral-300 dark:text-neutral-600" />
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Unable to load system information</p>
                </div>
              )}
            </div>

            {/* Links */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Links & Resources</h2>

              <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700">
                <a
                  href="https://github.com/Vasco0x4/Aida"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-neutral-500 dark:text-neutral-400" fill="currentColor" viewBox="0 0 24 24">
                      <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">GitHub Repository</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="https://www.vasco0x4.me/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Globe className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">Author Website</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="mailto:Vasco0x4@proton.me"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Mail className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">Contact Email</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="http://localhost:8001/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">API Documentation (Swagger)</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="http://localhost:8001/redoc"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Database className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">API Documentation (ReDoc)</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="https://github.com/ThePorgs/Exegol"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">Exegol Project</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>

                <a
                  href="https://modelcontextprotocol.io/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Info className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                    <span className="text-sm text-neutral-900 dark:text-neutral-100">MCP Protocol</span>
                  </div>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Settings;
