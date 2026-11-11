import React, { useState, useEffect, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  TextInput,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  VaakApi,
  ZeptoToolDefinition,
  ZeptoToolCallResult,
  ZeptoAllTestsReport,
  API_BASE_URL,
} from '@/services/api';

export default function ZeptoMcpScreen() {
  const [tools, setTools] = useState<ZeptoToolDefinition[]>([]);
  const [loadingTools, setLoadingTools] = useState<boolean>(true);
  const [toolInputs, setToolInputs] = useState<Record<string, string>>({});
  const [toolResults, setToolResults] = useState<Record<string, ZeptoToolCallResult>>({});
  const [executingTool, setExecutingTool] = useState<string | null>(null);
  const [forceUpstream, setForceUpstream] = useState<boolean>(false);
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [authStatus, setAuthStatus] = useState<{ is_authenticated: boolean; endpoint: string } | null>(null);
  const [pingResult, setPingResult] = useState<{ reachable: boolean; latency_ms: number; status_code?: number } | null>(
    null
  );
  const [isRunningAll, setIsRunningAll] = useState<boolean>(false);
  const [allTestsReport, setAllTestsReport] = useState<ZeptoAllTestsReport | null>(null);

  const loadToolsAndStatus = useCallback(async () => {
    try {
      setLoadingTools(true);
      const [toolsRes, authRes] = await Promise.all([
        VaakApi.getZeptoMcpTools(),
        VaakApi.getZeptoAuthStatus().catch(() => ({ is_authenticated: false, endpoint: 'https://mcp.zepto.co.in/mcp' })),
      ]);

      setTools(toolsRes.tools);
      setAuthStatus(authRes);

      // Prepopulate input json strings with default test inputs
      const initialInputs: Record<string, string> = {};
      for (const tool of toolsRes.tools) {
        initialInputs[tool.name] = JSON.stringify(tool.default_input || {}, null, 2);
      }
      setToolInputs(initialInputs);
    } catch (err) {
      console.error('Failed to load Zepto MCP tools:', err);
    } finally {
      setLoadingTools(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadToolsAndStatus();
  }, [loadToolsAndStatus]);

  const handlePing = async () => {
    try {
      setPingResult(null);
      const res = await VaakApi.pingZeptoMcp();
      setPingResult(res);
    } catch (err) {
      console.error('Ping failed:', err);
      setPingResult({ reachable: false, latency_ms: 0 });
    }
  };

  const handleConnectOAuth = () => {
    const loginUrl = `${API_BASE_URL}/api/v1/auth/zepto/login`;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.open(loginUrl, '_blank');
    } else {
      Alert.alert(
        'Connect Zepto Account',
        `Visit this URL in your browser to sign in via Zepto OTP:\n\n${loginUrl}`,
        [{ text: 'OK' }]
      );
    }
  };

  const handleExecuteTool = async (toolName: string) => {
    try {
      setExecutingTool(toolName);
      let parsedArgs: Record<string, any> = {};
      try {
        const raw = toolInputs[toolName] || '{}';
        parsedArgs = JSON.parse(raw);
      } catch {
        Alert.alert('Invalid JSON Input', `Please verify valid JSON arguments for ${toolName}.`);
        return;
      }

      const result = await VaakApi.callZeptoMcpTool(toolName, parsedArgs, forceUpstream);
      setToolResults((prev) => ({ ...prev, [toolName]: result }));
    } catch (err: any) {
      console.error(`Tool execution error for ${toolName}:`, err);
      Alert.alert('Execution Error', err.message || 'Failed to call Zepto MCP tool.');
    } finally {
      setExecutingTool(null);
    }
  };

  const handleResetInput = (tool: ZeptoToolDefinition) => {
    setToolInputs((prev) => ({
      ...prev,
      [tool.name]: JSON.stringify(tool.default_input || {}, null, 2),
    }));
  };

  const handleRunAllTests = async () => {
    try {
      setIsRunningAll(true);
      setAllTestsReport(null);
      const report = await VaakApi.runAllZeptoToolTests();
      setAllTestsReport(report);

      // Populate toolResults with individual test results
      const newResults: Record<string, ZeptoToolCallResult> = {};
      for (const res of report.results) {
        newResults[res.tool_name] = {
          tool_name: res.tool_name,
          input_arguments: res.input_arguments,
          raw_rpc_request: res.raw_rpc_request,
          status: res.status as any,
          status_code: 200,
          source: res.source as any,
          is_authenticated: report.is_authenticated,
          endpoint: report.endpoint,
          execution_time_ms: res.execution_time_ms,
          response: res.response_preview,
        };
      }
      setToolResults((prev) => ({ ...prev, ...newResults }));
    } catch (err: any) {
      console.error('Run all tests failed:', err);
      Alert.alert('Error', err.message || 'Failed to run full tool test suite.');
    } finally {
      setIsRunningAll(false);
    }
  };

  const categories = ['All', ...Array.from(new Set(tools.map((t) => t.category).filter(Boolean)))];

  const filteredTools =
    activeCategory === 'All' ? tools : tools.filter((t) => t.category === activeCategory);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.badge}>ZEPTO MODEL CONTEXT PROTOCOL</Text>
            <Text style={styles.title}>⚡ Zepto MCP Tools Console</Text>
            <Text style={styles.subtitle}>
              Universal Commerce Protocol (UCP) • Interactive Inspection & Testing
            </Text>
          </View>
        </View>

        {/* Status & Connection Dashboard Card */}
        <View style={styles.dashboardCard}>
          <View style={styles.dashRow}>
            <View style={styles.dashItem}>
              <Text style={styles.dashLabel}>Official Endpoint:</Text>
              <Text style={styles.dashValue} numberOfLines={1}>
                {authStatus?.endpoint || 'https://mcp.zepto.co.in/mcp'}
              </Text>
            </View>

            <TouchableOpacity style={styles.pingButton} onPress={handlePing}>
              <Text style={styles.pingButtonText}>
                {pingResult ? `⚡ ${pingResult.latency_ms}ms` : '📡 Ping Endpoint'}
              </Text>
            </TouchableOpacity>
          </View>

          <View style={styles.dashDivider} />

          <View style={styles.dashRow}>
            <View style={styles.authStatusBadge}>
              <View
                style={[
                  styles.statusDot,
                  { backgroundColor: authStatus?.is_authenticated ? '#10B981' : '#F59E0B' },
                ]}
              />
              <Text style={styles.authStatusText}>
                {authStatus?.is_authenticated ? 'Live Account Connected' : 'Sandbox Dark Store Mode'}
              </Text>
            </View>

            <TouchableOpacity style={styles.oauthButton} onPress={handleConnectOAuth}>
              <Text style={styles.oauthButtonText}>
                {authStatus?.is_authenticated ? '✓ Reconnect OAuth' : '🔑 Connect Zepto via OAuth'}
              </Text>
            </TouchableOpacity>
          </View>

          {pingResult && (
            <View style={styles.pingDetailsBox}>
              <Text style={styles.pingDetailsText}>
                {pingResult.reachable
                  ? `✓ Zepto Server Reachable (${pingResult.latency_ms} ms) • HTTP ${pingResult.status_code || 401} (Standard OAuth Bearer requirement)`
                  : '⚠️ Zepto endpoint ping failed or timed out.'}
              </Text>
            </View>
          )}
        </View>

        {/* Global Test Sweep Button & Mode Toggle */}
        <View style={styles.actionControlsRow}>
          <TouchableOpacity
            style={[styles.runAllButton, isRunningAll && styles.runAllButtonDisabled]}
            onPress={handleRunAllTests}
            disabled={isRunningAll}
          >
            {isRunningAll ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.runAllButtonText}>🚀 Run All {tools.length} Tools Test Suite</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.forceUpstreamPill, forceUpstream && styles.forceUpstreamPillActive]}
            onPress={() => setForceUpstream(!forceUpstream)}
          >
            <Text style={[styles.forceUpstreamText, forceUpstream && styles.forceUpstreamTextActive]}>
              {forceUpstream ? '🔴 Upstream HTTP Forced' : '🟢 Smart Auto Mode'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Sweep Test Summary Report */}
        {allTestsReport && (
          <View style={styles.reportCard}>
            <View style={styles.reportHeader}>
              <Text style={styles.reportTitle}>📊 Comprehensive Test Report</Text>
              <Text style={styles.reportMeta}>
                Total Time: {allTestsReport.total_execution_time_ms} ms
              </Text>
            </View>
            <View style={styles.reportStatsRow}>
              <View style={styles.statBox}>
                <Text style={styles.statNumber}>{allTestsReport.total_tools}</Text>
                <Text style={styles.statLabel}>Total Tools</Text>
              </View>
              <View style={styles.statBox}>
                <Text style={[styles.statNumber, { color: '#10B981' }]}>
                  {allTestsReport.passed_tools}
                </Text>
                <Text style={styles.statLabel}>Passed</Text>
              </View>
              <View style={styles.statBox}>
                <Text style={[styles.statNumber, { color: allTestsReport.failed_tools > 0 ? '#EF4444' : '#94A3B8' }]}>
                  {allTestsReport.failed_tools}
                </Text>
                <Text style={styles.statLabel}>Failed</Text>
              </View>
            </View>
          </View>
        )}

        {/* Category Filters */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll}>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat}
              style={[styles.categoryChip, activeCategory === cat && styles.categoryChipActive]}
              onPress={() => setActiveCategory(cat)}
            >
              <Text
                style={[
                  styles.categoryChipText,
                  activeCategory === cat && styles.categoryChipTextActive,
                ]}
              >
                {cat} {cat === 'All' ? `(${tools.length})` : ''}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Loading Spinner */}
        {loadingTools && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color="#6366F1" />
            <Text style={styles.loadingText}>Loading Zepto MCP tool registry...</Text>
          </View>
        )}

        {/* List of Tools */}
        {filteredTools.map((tool) => {
          const result = toolResults[tool.name];
          const isExecuting = executingTool === tool.name;
          const currentInput = toolInputs[tool.name] || '{}';

          return (
            <View key={tool.name} style={styles.toolCard}>
              {/* Tool Header */}
              <View style={styles.toolCardHeader}>
                <View style={styles.toolNameWrap}>
                  <Text style={styles.toolRpcBadge}>tools/call</Text>
                  <Text style={styles.toolName}>{tool.name}</Text>
                </View>
                {tool.category && (
                  <View style={styles.categoryBadge}>
                    <Text style={styles.categoryBadgeText}>{tool.category}</Text>
                  </View>
                )}
              </View>

              <Text style={styles.toolDescription}>{tool.description}</Text>

              {/* INPUT PARAMETERS SECTION */}
              <View style={styles.inputSection}>
                <View style={styles.inputSectionHeader}>
                  <Text style={styles.inputSectionTitle}>📝 INPUT PARAMETERS (Editable)</Text>
                  <TouchableOpacity onPress={() => handleResetInput(tool)}>
                    <Text style={styles.resetButtonText}>↺ Reset to Default</Text>
                  </TouchableOpacity>
                </View>

                <TextInput
                  style={styles.jsonInput}
                  multiline
                  value={currentInput}
                  onChangeText={(text) =>
                    setToolInputs((prev) => ({ ...prev, [tool.name]: text }))
                  }
                  placeholder="{}"
                  placeholderTextColor="#64748B"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              {/* EXECUTE BUTTON */}
              <TouchableOpacity
                style={[styles.executeButton, isExecuting && styles.executeButtonDisabled]}
                onPress={() => handleExecuteTool(tool.name)}
                disabled={isExecuting}
              >
                {isExecuting ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.executeButtonText}>🚀 Execute Tool Call</Text>
                )}
              </TouchableOpacity>

              {/* OUTPUT RESPONSE SECTION */}
              {result && (
                <View style={styles.outputSection}>
                  <View style={styles.outputHeader}>
                    <View style={styles.outputStatusRow}>
                      <View
                        style={[
                          styles.outputStatusBadge,
                          {
                            backgroundColor:
                              result.status === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                            borderColor: result.status === 'success' ? '#10B981' : '#EF4444',
                          },
                        ]}
                      >
                        <Text
                          style={[
                            styles.outputStatusText,
                            { color: result.status === 'success' ? '#10B981' : '#EF4444' },
                          ]}
                        >
                          {result.status === 'success' ? '✓ 200 OK' : `⚠️ Status ${result.status_code}`}
                        </Text>
                      </View>

                      <View
                        style={[
                          styles.outputSourceBadge,
                          {
                            backgroundColor:
                              result.source === 'live_mcp' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            borderColor: result.source === 'live_mcp' ? '#3B82F6' : '#F59E0B',
                          },
                        ]}
                      >
                        <Text
                          style={[
                            styles.outputSourceText,
                            { color: result.source === 'live_mcp' ? '#60A5FA' : '#FBBF24' },
                          ]}
                        >
                          {result.source === 'live_mcp' ? '🟢 Live Upstream MCP' : '🟡 Dark Store Sandbox'}
                        </Text>
                      </View>
                    </View>

                    <Text style={styles.latencyText}>{result.execution_time_ms} ms</Text>
                  </View>

                  {/* RAW JSON-RPC REQUEST SENT */}
                  <View style={styles.payloadBox}>
                    <Text style={styles.payloadLabel}>Full JSON-RPC 2.0 Request Sent:</Text>
                    <Text style={styles.codeText}>
                      {JSON.stringify(result.raw_rpc_request, null, 2)}
                    </Text>
                  </View>

                  {/* RESPONSE PAYLOAD */}
                  <View style={styles.payloadBox}>
                    <Text style={styles.payloadLabel}>Response Received:</Text>
                    <Text style={styles.codeText}>
                      {JSON.stringify(result.response || result.error, null, 2)}
                    </Text>
                  </View>

                  {result.note && (
                    <Text style={styles.resultNote}>💡 Note: {result.note}</Text>
                  )}
                </View>
              )}
            </View>
          );
        })}

        {/* Architectural Explainer Section */}
        <View style={styles.explainerCard}>
          <Text style={styles.explainerTitle}>
            💡 How Zepto MCP Delivers Real-Time Items & Resolves Location
          </Text>

          <View style={styles.explainerStep}>
            <Text style={styles.stepNum}>1</Text>
            <View style={styles.stepTextWrap}>
              <Text style={styles.stepTitle}>Hyperlocal Dark Store Inventory</Text>
              <Text style={styles.stepDesc}>
                Unlike traditional e-commerce, quick commerce (10-min delivery) does not use a central warehouse. Every neighborhood has an assigned micro-fulfillment center (dark store). All catalog items, stock counts, and prices are queried directly from that specific store's real-time inventory.
              </Text>
            </View>
          </View>

          <View style={styles.explainerStep}>
            <Text style={styles.stepNum}>2</Text>
            <View style={styles.stepTextWrap}>
              <Text style={styles.stepTitle}>Location Resolution via OAuth & UCP</Text>
              <Text style={styles.stepDesc}>
                When logging in via Zepto OAuth, the Bearer token binds to the user's phone number and saved addresses. The `search_location` tool (`dev.ucp.common.location.search`) and location lookup resolve GPS coordinates and PIN codes (e.g. 560038) to determine the exact dark store ID.
              </Text>
            </View>
          </View>

          <View style={styles.explainerStep}>
            <Text style={styles.stepNum}>3</Text>
            <View style={styles.stepTextWrap}>
              <Text style={styles.stepTitle}>Standard Model Context Protocol (MCP)</Text>
              <Text style={styles.stepDesc}>
                All requests adhere strictly to the JSON-RPC 2.0 MCP standard (`tools/call`, `tools/list`). AI agents can safely inspect product availability, manage user baskets, and prepare checkout orders with transparent customer confirmation.
              </Text>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0F1D',
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 80,
  },
  header: {
    marginBottom: 16,
  },
  badge: {
    color: '#818CF8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.2,
    marginBottom: 4,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    color: '#F8FAFC',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    color: '#94A3B8',
    lineHeight: 18,
  },
  dashboardCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 16,
  },
  dashRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  dashItem: {
    flex: 1,
  },
  dashLabel: {
    fontSize: 11,
    color: '#94A3B8',
    marginBottom: 2,
  },
  dashValue: {
    fontSize: 12,
    color: '#E2E8F0',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  pingButton: {
    backgroundColor: '#0F172A',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#475569',
  },
  pingButtonText: {
    color: '#38BDF8',
    fontSize: 12,
    fontWeight: '600',
  },
  dashDivider: {
    height: 1,
    backgroundColor: '#334155',
    marginVertical: 12,
  },
  authStatusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  authStatusText: {
    fontSize: 12,
    color: '#F1F5F9',
    fontWeight: '600',
  },
  oauthButton: {
    backgroundColor: '#6366F1',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  oauthButtonText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  pingDetailsBox: {
    marginTop: 10,
    backgroundColor: '#0F172A',
    padding: 8,
    borderRadius: 6,
  },
  pingDetailsText: {
    fontSize: 11,
    color: '#A5B4FC',
  },
  actionControlsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
    alignItems: 'center',
  },
  runAllButton: {
    flex: 1,
    backgroundColor: '#10B981',
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  runAllButtonDisabled: {
    opacity: 0.6,
  },
  runAllButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  forceUpstreamPill: {
    backgroundColor: '#1E293B',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  forceUpstreamPillActive: {
    borderColor: '#EF4444',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
  },
  forceUpstreamText: {
    fontSize: 11,
    color: '#94A3B8',
    fontWeight: '600',
  },
  forceUpstreamTextActive: {
    color: '#F87171',
  },
  reportCard: {
    backgroundColor: '#1E293B',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#10B981',
    marginBottom: 16,
  },
  reportHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  reportTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#F8FAFC',
  },
  reportMeta: {
    fontSize: 11,
    color: '#A5B4FC',
  },
  reportStatsRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  statBox: {
    alignItems: 'center',
  },
  statNumber: {
    fontSize: 18,
    fontWeight: '800',
    color: '#F8FAFC',
  },
  statLabel: {
    fontSize: 10,
    color: '#94A3B8',
    marginTop: 2,
  },
  categoryScroll: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  categoryChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: '#1E293B',
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  categoryChipActive: {
    backgroundColor: '#4F46E5',
    borderColor: '#6366F1',
  },
  categoryChipText: {
    fontSize: 12,
    color: '#94A3B8',
    fontWeight: '600',
  },
  categoryChipTextActive: {
    color: '#FFFFFF',
  },
  centerContainer: {
    padding: 40,
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    color: '#94A3B8',
    fontSize: 13,
  },
  toolCard: {
    backgroundColor: '#131D31',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 16,
  },
  toolCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  toolNameWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  toolRpcBadge: {
    backgroundColor: '#312E81',
    color: '#C7D2FE',
    fontSize: 10,
    fontWeight: '700',
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: 4,
  },
  toolName: {
    fontSize: 16,
    fontWeight: '700',
    color: '#F8FAFC',
  },
  categoryBadge: {
    backgroundColor: '#1E293B',
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 6,
  },
  categoryBadgeText: {
    fontSize: 10,
    color: '#94A3B8',
  },
  toolDescription: {
    fontSize: 12,
    color: '#94A3B8',
    marginBottom: 14,
    lineHeight: 16,
  },
  inputSection: {
    marginBottom: 12,
  },
  inputSectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  inputSectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: '#E2E8F0',
    letterSpacing: 0.5,
  },
  resetButtonText: {
    fontSize: 11,
    color: '#818CF8',
    fontWeight: '600',
  },
  jsonInput: {
    backgroundColor: '#0A0F1D',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 8,
    padding: 10,
    color: '#38BDF8',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    fontSize: 12,
    minHeight: 65,
    textAlignVertical: 'top',
  },
  executeButton: {
    backgroundColor: '#4F46E5',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  executeButtonDisabled: {
    opacity: 0.6,
  },
  executeButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  outputSection: {
    backgroundColor: '#0A0F1D',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  outputHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  outputStatusRow: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  outputStatusBadge: {
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 6,
    borderWidth: 1,
  },
  outputStatusText: {
    fontSize: 11,
    fontWeight: '700',
  },
  outputSourceBadge: {
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 6,
    borderWidth: 1,
  },
  outputSourceText: {
    fontSize: 11,
    fontWeight: '600',
  },
  latencyText: {
    fontSize: 11,
    color: '#94A3B8',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  payloadBox: {
    marginBottom: 10,
  },
  payloadLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#64748B',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  codeText: {
    backgroundColor: '#060A13',
    padding: 8,
    borderRadius: 6,
    color: '#A5B4FC',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    lineHeight: 16,
  },
  resultNote: {
    fontSize: 11,
    color: '#FCD34D',
    marginTop: 4,
    lineHeight: 15,
  },
  explainerCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#334155',
    marginTop: 10,
  },
  explainerTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#F8FAFC',
    marginBottom: 14,
  },
  explainerStep: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 14,
  },
  stepNum: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#4F46E5',
    color: '#FFFFFF',
    textAlign: 'center',
    lineHeight: 24,
    fontWeight: '700',
    fontSize: 12,
  },
  stepTextWrap: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#E2E8F0',
    marginBottom: 2,
  },
  stepDesc: {
    fontSize: 12,
    color: '#94A3B8',
    lineHeight: 17,
  },
});
