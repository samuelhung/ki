export function createChainDetailCache() {
  const chats = new Map();
  const reports = new Map();

  return {
    getChat(chainName) {
      return (chats.get(chainName) || []).map((message) => ({ ...message }));
    },
    setChat(chainName, messages) {
      chats.set(chainName, messages.map((message) => ({ ...message })));
    },
    clearChat(chainName) {
      chats.delete(chainName);
    },
    getReport(chainName) {
      const entry = reports.get(chainName);
      return entry ? { ...entry } : null;
    },
    setReport(chainName, entry) {
      reports.set(chainName, { ...entry });
    },
    clearReport(chainName) {
      reports.delete(chainName);
    },
  };
}
