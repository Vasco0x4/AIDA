import { useState, useEffect } from 'react';
import { X, Globe, Code, Server, Smartphone, Network, FileText, ChevronRight, ArrowLeft } from 'lucide-react';
import apiClient from '../../services/api';

const TEMPLATE_ICONS = {
  globe: Globe,
  code: Code,
  server: Server,
  smartphone: Smartphone,
  network: Network,
  file: FileText,
};

const CreateAssessmentModal = ({ onClose, onSuccess }) => {
  const [step, setStep] = useState('template'); // 'template' | 'form'
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    client_name: '',
    scope: '',
    limitations: '',
    objectives: '',
    target_domains: '',
    ip_scopes: '',
    start_date: '',
    end_date: '',
    category: '',
    environment: 'non_specifie',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const { data } = await apiClient.get('/templates');
      setTemplates(data);
    } catch (e) {
      // Templates endpoint might not exist yet, continue with blank
      setTemplates([]);
    }
  };

  const selectTemplate = async (templateId) => {
    if (templateId === 'blank') {
      setSelectedTemplate({ id: 'blank', name: 'Blank Assessment' });
      setStep('form');
      return;
    }

    try {
      const { data } = await apiClient.get(`/templates/${templateId}`);
      setSelectedTemplate(data);
      // Auto-fill form from template
      setFormData(prev => ({
        ...prev,
        scope: data.default_scope || prev.scope,
        limitations: data.default_limitations || prev.limitations,
        objectives: data.default_objectives || prev.objectives,
        category: data.category || prev.category,
      }));
      setStep('form');
    } catch (e) {
      setStep('form');
    }
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const payload = {
        ...formData,
        target_domains: formData.target_domains
          .split(',')
          .map(d => d.trim())
          .filter(Boolean),
        ip_scopes: formData.ip_scopes
          .split(',')
          .map(ip => ip.trim())
          .filter(Boolean),
        start_date: formData.start_date || null,
        end_date: formData.end_date || null,
        category: formData.category || null,
      };

      const response = await apiClient.post('/assessments', payload);
      const assessmentId = response.data.id;

      // If template has phases, create sections
      if (selectedTemplate?.phases?.length > 0) {
        for (const phase of selectedTemplate.phases) {
          try {
            await apiClient.post(`/assessments/${assessmentId}/sections`, {
              section_number: phase.number,
              title: phase.title,
              content: phase.content,
            });
          } catch (e) {
            // Continue even if a section fails
          }
        }
      }

      onSuccess(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create assessment');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-black/20 dark:bg-black/70 backdrop-blur-sm z-50 animate-in"
        onClick={onClose}
      />

      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-2xl bg-white dark:bg-neutral-800 rounded-xl shadow-strong animate-slide-up">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
            <div className="flex items-center gap-3">
              {step === 'form' && (
                <button onClick={() => setStep('template')} className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded">
                  <ArrowLeft className="w-4 h-4 text-neutral-500" />
                </button>
              )}
              <div>
                <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                  {step === 'template' ? 'Choose Template' : 'Create Assessment'}
                </h2>
                {step === 'form' && selectedTemplate && selectedTemplate.id !== 'blank' && (
                  <p className="text-xs text-primary-600 dark:text-primary-400 mt-0.5">
                    Template: {selectedTemplate.name}
                  </p>
                )}
              </div>
            </div>
            <button onClick={onClose} className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded transition-colors">
              <X className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
            </button>
          </div>

          {/* Template Selection */}
          {step === 'template' && (
            <div className="p-6 max-h-[calc(100vh-200px)] overflow-y-auto">
              <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
                Select a template to pre-fill phases, scope, and tooling recommendations — or start blank.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {templates.map(tpl => {
                  const Icon = TEMPLATE_ICONS[tpl.icon] || FileText;
                  return (
                    <button
                      key={tpl.id}
                      onClick={() => selectTemplate(tpl.id)}
                      className="flex items-start gap-3 p-4 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary-400 dark:hover:border-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/10 transition-all text-left group"
                    >
                      <div className="w-10 h-10 rounded-lg bg-neutral-100 dark:bg-neutral-700 flex items-center justify-center shrink-0 group-hover:bg-primary-100 dark:group-hover:bg-primary-900/30">
                        <Icon className="w-5 h-5 text-neutral-500 group-hover:text-primary-600 dark:group-hover:text-primary-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{tpl.name}</span>
                          <ChevronRight className="w-4 h-4 text-neutral-300 group-hover:text-primary-500" />
                        </div>
                        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">{tpl.description}</p>
                        {tpl.suggested_tools?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {tpl.suggested_tools.slice(0, 4).map(tool => (
                              <span key={tool} className="px-1.5 py-0.5 text-[9px] font-mono bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 rounded">
                                {tool}
                              </span>
                            ))}
                            {tpl.suggested_tools.length > 4 && (
                              <span className="px-1.5 py-0.5 text-[9px] text-neutral-400">
                                +{tpl.suggested_tools.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Form */}
          {step === 'form' && (
            <>
              <form onSubmit={handleSubmit} className="p-6 space-y-5 max-h-[calc(100vh-200px)] overflow-y-auto">
                {error && (
                  <div className="px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400">
                    {error}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Assessment Name *</label>
                  <input type="text" required value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="Q4 2025 Pentest" className="input" />
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Client Name</label>
                  <input type="text" value={formData.client_name} onChange={(e) => setFormData({ ...formData, client_name: e.target.value })} placeholder="Acme Corporation" className="input" />
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Category</label>
                  <select value={formData.category} onChange={(e) => setFormData({ ...formData, category: e.target.value })} className="input">
                    <option value="">Select category</option>
                    <option value="API">API</option>
                    <option value="Website">Website</option>
                    <option value="External Infra">External Infra</option>
                    <option value="Internal Infra">Internal Infra</option>
                    <option value="Mobile">Mobile</option>
                    <option value="Cloud">Cloud</option>
                    <option value="General">General</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Environment</label>
                  <select value={formData.environment} onChange={(e) => setFormData({ ...formData, environment: e.target.value })} className="input">
                    <option value="non_specifie">Not specified</option>
                    <option value="production">Production</option>
                    <option value="dev">Development</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Scope</label>
                  <textarea value={formData.scope} onChange={(e) => setFormData({ ...formData, scope: e.target.value })} placeholder="*.example.com, web applications, API endpoints..." rows={3} className="input resize-none" />
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Objectives</label>
                  <textarea value={formData.objectives} onChange={(e) => setFormData({ ...formData, objectives: e.target.value })} placeholder="Identify vulnerabilities..." rows={2} className="input resize-none" />
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Limitations</label>
                  <textarea value={formData.limitations} onChange={(e) => setFormData({ ...formData, limitations: e.target.value })} placeholder="No DoS attacks, no social engineering..." rows={2} className="input resize-none" />
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Target Domains</label>
                  <input type="text" value={formData.target_domains} onChange={(e) => setFormData({ ...formData, target_domains: e.target.value })} placeholder="example.com, app.example.com" className="input" />
                  <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">Comma-separated list</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">IP Scopes</label>
                  <input type="text" value={formData.ip_scopes} onChange={(e) => setFormData({ ...formData, ip_scopes: e.target.value })} placeholder="192.168.1.0/24, 10.0.0.0/16" className="input" />
                  <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">Comma-separated list</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Start Date</label>
                    <input type="date" value={formData.start_date} onChange={(e) => setFormData({ ...formData, start_date: e.target.value })} className="input" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">End Date</label>
                    <input type="date" value={formData.end_date} onChange={(e) => setFormData({ ...formData, end_date: e.target.value })} className="input" />
                  </div>
                </div>
              </form>

              <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900">
                <button type="button" onClick={onClose} className="btn btn-secondary" disabled={loading}>Cancel</button>
                <button type="button" onClick={handleSubmit} className="btn btn-primary" disabled={loading}>
                  {loading ? 'Creating...' : 'Create Assessment'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default CreateAssessmentModal;
