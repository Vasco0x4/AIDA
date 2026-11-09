export function createNvdService(client) {
  return {
    async getDigest() {
      const { data } = await client.get('/nvd/digest');
      return data;
    },
    async getStatus() {
      const { data } = await client.get('/nvd/status');
      return data;
    },
    async refresh() {
      const { data } = await client.post('/nvd/refresh');
      return data;
    },
    async updateSchedule(changes) {
      const { data } = await client.put('/nvd/schedule', changes);
      return data;
    },
  };
}

export default createNvdService;
