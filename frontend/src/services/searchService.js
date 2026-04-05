import apiClient from './api';

class SearchService {
  /**
   * New unified search using the optimized backend endpoint
   * 1 API call instead of 31!
   */
  async searchAll(query) {
    if (!query.trim()) return [];

    try {
      const response = await apiClient.get('/search', {
        params: {
          q: query,
          limit: 50
        }
      });

      // Return results directly from unified endpoint
      return response.data.results || [];
    } catch (error) {
      console.error('Search error:', error);
      return [];
    }
  }

  /**
   * Search with type filtering
   */
  async searchByType(query, types) {
    if (!query.trim()) return [];

    try {
      const response = await apiClient.get('/search', {
        params: {
          q: query,
          types: types.join(','),
          limit: 50
        }
      });

      return response.data.results || [];
    } catch (error) {
      console.error('Search error:', error);
      return [];
    }
  }

  /**
   * Advanced search with severity, status, and date filters
   */
  async searchAdvanced(query, { types, severity, status, dateFrom, dateTo } = {}) {
    if (!query.trim()) return { results: [], total: 0, execution_time: 0 };

    try {
      const params = { q: query, limit: 50 };
      if (types) params.types = Array.isArray(types) ? types.join(',') : types;
      if (severity && severity.length) params.severity = severity.join(',');
      if (status && status.length) params.status = status.join(',');
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const response = await apiClient.get('/search', { params });
      return response.data;
    } catch (error) {
      console.error('Search error:', error);
      return { results: [], total: 0, execution_time: 0 };
    }
  }

  /**
   * Get grouped results
   */
  async searchGrouped(query) {
    if (!query.trim()) return {};

    try {
      const response = await apiClient.get('/search', {
        params: {
          q: query,
          limit: 50
        }
      });

      return response.data.grouped || {};
    } catch (error) {
      console.error('Search error:', error);
      return {};
    }
  }

  // Old methods kept for backward compatibility (but not used anymore)

  async searchAssessments(query) {
    try {
      const response = await apiClient.get('/assessments');
      const assessments = response.data;
      
      const filteredAssessments = assessments
        .filter(assessment => 
          assessment.name.toLowerCase().includes(query.toLowerCase()) ||
          (assessment.client_name && assessment.client_name.toLowerCase().includes(query.toLowerCase())) ||
          (assessment.scope && assessment.scope.toLowerCase().includes(query.toLowerCase()))
        );
      
      console.log('Found assessments:', filteredAssessments);
      
      return filteredAssessments.map(assessment => ({
        type: 'assessment',
        id: assessment.id,
        title: assessment.name,
        subtitle: assessment.client_name || 'No client',
        description: assessment.scope ? assessment.scope.substring(0, 100) + '...' : 'No scope defined',
        url: `/assessments/${assessment.id}`,
        icon: 'FileText'
      }));
    } catch (error) {
      console.error('Error searching assessments:', error);
      return [];
    }
  }

  async searchCommands(query) {
    try {
      // Get all assessments first
      const assessmentsResponse = await apiClient.get('/assessments');
      const assessments = assessmentsResponse.data;
      
      const results = [];
      
      for (const assessment of assessments) {
        try {
          const commandsResponse = await apiClient.get(`/assessments/${assessment.id}/commands`);
          const commands = commandsResponse.data;
          
          const matchingCommands = commands.filter(command =>
            command.command.toLowerCase().includes(query.toLowerCase()) ||
            (command.stdout && command.stdout.toLowerCase().includes(query.toLowerCase())) ||
            (command.stderr && command.stderr.toLowerCase().includes(query.toLowerCase()))
          );
          
          matchingCommands.forEach(command => {
            results.push({
              type: 'command',
              id: command.id,
              title: command.command,
              subtitle: `${assessment.name} • ${command.container_name}`,
              description: command.stdout ? command.stdout.substring(0, 100) + '...' : 'No output',
              url: `/assessments/${assessment.id}#command-${command.id}`,
              icon: 'Terminal',
              metadata: {
                success: command.success,
                executionTime: command.execution_time,
                phase: command.phase,
                commandId: command.id
              }
            });
          });
        } catch (error) {
          // Skip if commands endpoint fails
          continue;
        }
      }
      
      return results;
    } catch (error) {
      console.error('Error searching commands:', error);
      return [];
    }
  }

  async searchFindings(query) {
    try {
      // Get all assessments first
      const assessmentsResponse = await apiClient.get('/assessments');
      const assessments = assessmentsResponse.data;
      
      const results = [];
      
      for (const assessment of assessments) {
        try {
          const cardsResponse = await apiClient.get(`/assessments/${assessment.id}/cards`);
          const cards = cardsResponse.data;
          
          const matchingCards = cards.filter(card =>
            card.title.toLowerCase().includes(query.toLowerCase()) ||
            (card.technical_analysis && card.technical_analysis.toLowerCase().includes(query.toLowerCase())) ||
            (card.notes && card.notes.toLowerCase().includes(query.toLowerCase())) ||
            (card.context && card.context.toLowerCase().includes(query.toLowerCase()))
          );
          
          matchingCards.forEach(card => {
            results.push({
              type: 'finding',
              id: card.id,
              title: card.title,
              subtitle: `${assessment.name} • ${card.card_type} • ${card.section_number}`,
              description: card.technical_analysis || card.notes || card.context || 'No description',
              url: `/assessments/${assessment.id}#card-${card.id}`,
              icon: card.card_type === 'finding' ? 'Shield' : card.card_type === 'observation' ? 'Eye' : 'Info',
              metadata: {
                severity: card.severity,
                cardType: card.card_type,
                sectionNumber: card.section_number,
                cardId: card.id
              }
            });
          });
        } catch (error) {
          // Skip if cards endpoint fails
          continue;
        }
      }
      
      return results;
    } catch (error) {
      console.error('Error searching findings:', error);
      return [];
    }
  }

  async searchReconData(query) {
    try {
      // Get all assessments first
      const assessmentsResponse = await apiClient.get('/assessments');
      const assessments = assessmentsResponse.data;
      
      const results = [];
      
      for (const assessment of assessments) {
        try {
          const reconResponse = await apiClient.get(`/assessments/${assessment.id}/recon`);
          const reconData = reconResponse.data;
          
          const matchingRecon = reconData.filter(item =>
            item.name.toLowerCase().includes(query.toLowerCase()) ||
            (item.details && JSON.stringify(item.details).toLowerCase().includes(query.toLowerCase()))
          );
          
          matchingRecon.forEach(item => {
            results.push({
              type: 'recon',
              id: item.id,
              title: item.name,
              subtitle: `${assessment.name} • ${item.data_type} • ${item.discovered_in_phase}`,
              description: item.details ? Object.entries(item.details).map(([k, v]) => `${k}: ${v}`).join(', ') : 'No details',
              url: `/assessments/${assessment.id}#recon-${item.id}`,
              icon: 'Target',
              metadata: {
                dataType: item.data_type,
                phase: item.discovered_in_phase,
                details: item.details,
                reconId: item.id
              }
            });
          });
        } catch (error) {
          // Skip if recon endpoint fails
          continue;
        }
      }
      
      return results;
    } catch (error) {
      console.error('Error searching recon data:', error);
      return [];
    }
  }
}

export default new SearchService();
