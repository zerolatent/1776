import { StatusBar } from "expo-status-bar";
import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  addWatch,
  getAlerts,
  getBrief,
  getForecasts,
  getRule,
  getSources,
  investigateRule,
  listRules,
  login,
  submitForecast
} from "./src/api";
import { AlertItem, Brief, ForecastCard, RuleCard, RuleDetail, Session, SourceRef } from "./src/types";

type Tab = "home" | "watch" | "alerts" | "profile";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [tab, setTab] = useState<Tab>("home");
  const [rules, setRules] = useState<RuleCard[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRules()
      .catch((error) => Alert.alert("1776 is offline", error.message))
      .finally(() => setLoading(false));
  }, []);

  async function loadRules() {
    const items = await listRules();
    setRules(items);
  }

  const selected = useMemo(() => rules.find((rule) => rule.id === selectedRuleId), [rules, selectedRuleId]);

  if (loading) {
    return <Centered label="Preparing your civic brief" />;
  }

  if (!session) {
    return <LoginScreen onLogin={setSession} />;
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <View>
          <Text style={styles.brand}>1776</Text>
          <Text style={styles.subtitle}>AI accountability for public rules</Text>
        </View>
        <View style={styles.livePill}>
          <Text style={styles.liveText}>AI guided</Text>
        </View>
      </View>

      {selected ? (
        <RuleDetailScreen ruleId={selected.id} onBack={() => setSelectedRuleId(null)} onRefresh={loadRules} />
      ) : tab === "home" ? (
        <HomeScreen rules={rules} onSelect={setSelectedRuleId} onRefresh={loadRules} />
      ) : tab === "watch" ? (
        <WatchScreen rules={rules} />
      ) : tab === "alerts" ? (
        <AlertsScreen />
      ) : (
        <ProfileScreen session={session} />
      )}

      {!selected && <TabBar active={tab} onChange={setTab} />}
    </SafeAreaView>
  );
}

function LoginScreen({ onLogin }: { onLogin: (session: Session) => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!email.trim() || !name.trim()) {
      Alert.alert("Name and email required", "1776 uses this for watchlists and civic forecasting reputation.");
      return;
    }
    setBusy(true);
    try {
      const session = await login(email.trim(), name.trim());
      onLogin(session);
    } catch (error) {
      Alert.alert("Login failed", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.brand}>1776</Text>
        <Text style={styles.screenTitle}>AI accountability for public rules</Text>
        <Text style={styles.screenHelp}>Create a lightweight account for watchlists, alerts, and forecasting reputation.</Text>
        <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="Name" />
        <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="Email" autoCapitalize="none" keyboardType="email-address" />
        <Pressable style={styles.primaryButton} onPress={submit} disabled={busy}>
          <Ionicons name="person" size={18} color="#fff" />
          <Text style={styles.primaryButtonText}>{busy ? "Signing in..." : "Continue"}</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function HomeScreen({ rules, onSelect, onRefresh }: { rules: RuleCard[]; onSelect: (id: number) => void; onRefresh: () => void }) {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.screenTitle}>What needs attention?</Text>
      <Text style={styles.screenHelp}>1776 reads the register and shows the few rule actions most likely to matter.</Text>
      <Pressable style={styles.secondaryButton} onPress={onRefresh}>
        <Ionicons name="refresh" size={17} color="#26413C" />
        <Text style={styles.secondaryButtonText}>Refresh feed</Text>
      </Pressable>
      {rules.map((rule) => (
        <RuleCardView key={rule.id} rule={rule} onPress={() => onSelect(rule.id)} />
      ))}
    </ScrollView>
  );
}

function RuleCardView({ rule, onPress }: { rule: RuleCard; onPress: () => void }) {
  return (
    <Pressable style={styles.card} onPress={onPress}>
      <View style={styles.rowBetween}>
        <Text style={styles.status}>{rule.action_type}</Text>
        <Text style={styles.signal}>{rule.heard_signal}</Text>
      </View>
      <Text style={styles.cardTitle}>{rule.title}</Text>
      <Text style={styles.meta}>{rule.agency}</Text>
      <Text style={styles.summary}>{rule.why_matters}</Text>
      <View style={styles.cardFooter}>
        <Text style={styles.tac}>{rule.tac_citation}</Text>
        {rule.forecast_count > 0 && <Text style={styles.forecastBadge}>{rule.forecast_count} forecasts</Text>}
      </View>
    </Pressable>
  );
}

function RuleDetailScreen({ ruleId, onBack, onRefresh }: { ruleId: number; onBack: () => void; onRefresh: () => void }) {
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [forecasts, setForecasts] = useState<ForecastCard[]>([]);
  const [showEvidence, setShowEvidence] = useState(false);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    load();
  }, [ruleId]);

  async function load() {
    setBusy(true);
    try {
      const [detail, briefData, sourceData, forecastData] = await Promise.all([
        getRule(ruleId),
        getBrief(ruleId),
        getSources(ruleId),
        getForecasts(ruleId)
      ]);
      setRule(detail);
      setBrief(briefData);
      setSources(sourceData);
      setForecasts(forecastData);
    } finally {
      setBusy(false);
    }
  }

  async function runInvestigation() {
    setBusy(true);
    try {
      await investigateRule(ruleId);
      await load();
      onRefresh();
    } catch (error) {
      Alert.alert("Investigation failed", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }

  if (busy || !rule || !brief) {
    return <Centered label="AI is reading the record" />;
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Pressable style={styles.backButton} onPress={onBack}>
        <Ionicons name="chevron-back" size={18} color="#26413C" />
        <Text style={styles.secondaryButtonText}>Back</Text>
      </Pressable>

      <View style={styles.heroCard}>
        <Text style={styles.status}>{rule.status}</Text>
        <Text style={styles.heroTitle}>{rule.title}</Text>
        <Text style={styles.meta}>{rule.agency}</Text>
        <Text style={styles.heroSummary}>{brief.plain_summary}</Text>
        <Pressable style={styles.primaryButton} onPress={runInvestigation}>
          <Ionicons name="sparkles" size={18} color="#fff" />
          <Text style={styles.primaryButtonText}>Run AI brief</Text>
        </Pressable>
      </View>

      <Section title="Who is affected">
        <View style={styles.pillWrap}>
          {brief.affected_groups.map((group) => (
            <Text key={group} style={styles.groupPill}>
              {group}
            </Text>
          ))}
        </View>
      </Section>

      <Section title="Were people heard?">
        <Text style={styles.bigSignal}>{brief.public_heard_signal}</Text>
        <Text style={styles.summary}>{brief.body}</Text>
        {rule.top_concerns.slice(0, 3).map((item) => (
          <View key={item.id} style={styles.concernBox}>
            <Text style={styles.concernLabel}>{item.disposition}</Text>
            <Text style={styles.concernText}>{item.concern}</Text>
            <Text style={styles.responseText}>{item.agency_response}</Text>
          </View>
        ))}
      </Section>

      {forecasts.length > 0 && (
        <Section title="Forecasts">
          {forecasts.map((forecast) => (
            <ForecastView key={forecast.id} forecast={forecast} onSubmitted={load} />
          ))}
        </Section>
      )}

      <Pressable style={styles.secondaryButton} onPress={() => setShowEvidence(!showEvidence)}>
        <Ionicons name="document-text-outline" size={17} color="#26413C" />
        <Text style={styles.secondaryButtonText}>{showEvidence ? "Hide sources" : "View sources"}</Text>
      </Pressable>
      {showEvidence && <SourceList sources={sources} />}
    </ScrollView>
  );
}

function ForecastView({ forecast, onSubmitted }: { forecast: ForecastCard; onSubmitted: () => void }) {
  async function setProbability(probability: number) {
    try {
      await submitForecast(forecast.id, probability);
      await onSubmitted();
    } catch (error) {
      Alert.alert("Forecast not saved", error instanceof Error ? error.message : "Unknown error");
    }
  }

  return (
    <View style={styles.forecastCard}>
      <Text style={styles.forecastQuestion}>{forecast.question}</Text>
      <Text style={styles.meta}>Crowd: {Math.round(forecast.aggregate_probability * 100)}%</Text>
      <View style={styles.probRow}>
        {[0.25, 0.5, 0.75].map((value) => (
          <Pressable key={value} style={styles.probButton} onPress={() => setProbability(value)}>
            <Text style={styles.probText}>{Math.round(value * 100)}%</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.receipt}>{forecast.source_of_truth}</Text>
    </View>
  );
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  return (
    <View style={styles.sourceList}>
      {sources.map((source) => (
        <Pressable key={source.id} style={styles.sourceItem} onPress={() => Linking.openURL(source.url)}>
          <Text style={styles.sourceTitle}>{source.label}</Text>
          <Text style={styles.sourceSnippet}>{source.snippet}</Text>
          <Text style={styles.receipt}>Tap to open receipt</Text>
        </Pressable>
      ))}
    </View>
  );
}

function WatchScreen({ rules }: { rules: RuleCard[] }) {
  const [value, setValue] = useState("TCEQ");

  async function save() {
    try {
      await addWatch("keyword", value);
      Alert.alert("Watchlist saved", "1776 will create in-app alerts for matching rule actions.");
    } catch (error) {
      Alert.alert("Watchlist failed", error instanceof Error ? error.message : "Unknown error");
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.screenTitle}>Watch a topic</Text>
      <Text style={styles.screenHelp}>Pick one agency, topic, or rule citation. 1776 keeps the alert short.</Text>
      <TextInput style={styles.input} value={value} onChangeText={setValue} placeholder="Agency, keyword, or rule citation" />
      <Pressable style={styles.primaryButton} onPress={save}>
        <Ionicons name="notifications" size={18} color="#fff" />
        <Text style={styles.primaryButtonText}>Create watch</Text>
      </Pressable>
      {rules.slice(0, 2).map((rule) => (
        <View key={rule.id} style={styles.tipCard}>
          <Text style={styles.meta}>Suggested watch</Text>
          <Text style={styles.cardTitle}>{rule.agency}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

function AlertsScreen() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  useEffect(() => {
    getAlerts().then(setAlerts).catch(() => setAlerts([]));
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.screenTitle}>Alerts</Text>
      <Text style={styles.screenHelp}>AI-written updates from your watchlist.</Text>
      {alerts.length === 0 ? (
        <Text style={styles.empty}>No alerts yet. Add a watch topic first.</Text>
      ) : (
        alerts.map((alert) => (
          <Pressable key={alert.id} style={styles.card} onPress={() => Linking.openURL(alert.source_url)}>
            <Text style={styles.cardTitle}>{alert.title}</Text>
            <Text style={styles.summary}>{alert.body}</Text>
            <Text style={styles.receipt}>Source receipt</Text>
          </Pressable>
        ))
      )}
    </ScrollView>
  );
}

function ProfileScreen({ session }: { session: Session | null }) {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.screenTitle}>Profile</Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{session?.name ?? "Citizen"}</Text>
        <Text style={styles.meta}>{session?.email ?? "No email"}</Text>
        <Text style={styles.bigSignal}>50</Text>
        <Text style={styles.summary}>Starting civic forecasting reputation</Text>
      </View>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function TabBar({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  const tabs: Array<[Tab, keyof typeof Ionicons.glyphMap, string]> = [
    ["home", "home-outline", "Home"],
    ["watch", "eye-outline", "Watch"],
    ["alerts", "notifications-outline", "Alerts"],
    ["profile", "person-outline", "Profile"]
  ];
  return (
    <View style={styles.tabBar}>
      {tabs.map(([tab, icon, label]) => (
        <Pressable key={tab} style={styles.tab} onPress={() => onChange(tab)}>
          <Ionicons name={icon} size={21} color={active === tab ? "#1F6F5B" : "#6C756F"} />
          <Text style={[styles.tabText, active === tab && styles.tabTextActive]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function Centered({ label }: { label: string }) {
  return (
    <SafeAreaView style={styles.centered}>
      <ActivityIndicator />
      <Text style={styles.screenHelp}>{label}</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#F7F8F3" },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#F7F8F3", gap: 12 },
  header: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  brand: { fontSize: 26, fontWeight: "800", color: "#182621" },
  subtitle: { fontSize: 13, color: "#59645E", marginTop: 2 },
  livePill: { backgroundColor: "#DDECE4", paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  liveText: { color: "#1F6F5B", fontWeight: "700", fontSize: 12 },
  content: { padding: 20, paddingBottom: 110 },
  screenTitle: { fontSize: 28, fontWeight: "800", color: "#182621" },
  screenHelp: { color: "#59645E", fontSize: 15, lineHeight: 21, marginTop: 6, marginBottom: 14 },
  card: {
    backgroundColor: "#FFFFFF",
    borderRadius: 8,
    padding: 16,
    marginTop: 14,
    borderWidth: 1,
    borderColor: "#E4E7DF"
  },
  heroCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 8,
    padding: 18,
    borderWidth: 1,
    borderColor: "#E4E7DF"
  },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  status: { color: "#1F6F5B", fontWeight: "800", fontSize: 12, textTransform: "uppercase" },
  signal: { color: "#8A5A1E", fontWeight: "700", fontSize: 12 },
  cardTitle: { color: "#182621", fontSize: 17, fontWeight: "800", marginTop: 8 },
  heroTitle: { color: "#182621", fontSize: 24, fontWeight: "800", marginTop: 8 },
  meta: { color: "#6C756F", fontSize: 13, marginTop: 5 },
  summary: { color: "#33423B", fontSize: 15, lineHeight: 22, marginTop: 10 },
  heroSummary: { color: "#33423B", fontSize: 16, lineHeight: 23, marginTop: 12 },
  cardFooter: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 14 },
  tac: { color: "#59645E", fontWeight: "700", fontSize: 12 },
  forecastBadge: { color: "#1F6F5B", fontWeight: "800", fontSize: 12 },
  primaryButton: {
    backgroundColor: "#1F6F5B",
    borderRadius: 8,
    paddingVertical: 13,
    paddingHorizontal: 14,
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8
  },
  primaryButtonText: { color: "#FFFFFF", fontWeight: "800", fontSize: 15 },
  secondaryButton: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#C8D3CB",
    paddingVertical: 11,
    paddingHorizontal: 13,
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8
  },
  secondaryButtonText: { color: "#26413C", fontWeight: "800", fontSize: 14 },
  backButton: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", marginBottom: 12 },
  section: { marginTop: 20 },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: "#182621", marginBottom: 8 },
  pillWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  groupPill: { backgroundColor: "#E9EFEA", color: "#26413C", paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, fontWeight: "700" },
  bigSignal: { fontSize: 28, color: "#1F6F5B", fontWeight: "900", marginTop: 6 },
  concernBox: { backgroundColor: "#FFFFFF", borderRadius: 8, padding: 14, marginTop: 10, borderWidth: 1, borderColor: "#E4E7DF" },
  concernLabel: { color: "#8A5A1E", fontSize: 12, fontWeight: "800", textTransform: "uppercase" },
  concernText: { color: "#182621", fontSize: 15, fontWeight: "700", marginTop: 6 },
  responseText: { color: "#59645E", fontSize: 14, lineHeight: 20, marginTop: 6 },
  forecastCard: { backgroundColor: "#FFFFFF", borderRadius: 8, padding: 14, marginTop: 10, borderWidth: 1, borderColor: "#E4E7DF" },
  forecastQuestion: { fontSize: 16, fontWeight: "800", color: "#182621" },
  probRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  probButton: { flex: 1, borderRadius: 8, backgroundColor: "#E9EFEA", paddingVertical: 10, alignItems: "center" },
  probText: { color: "#1F6F5B", fontWeight: "900" },
  sourceList: { marginTop: 10, gap: 10 },
  sourceItem: { backgroundColor: "#FFFFFF", borderRadius: 8, padding: 14, borderWidth: 1, borderColor: "#E4E7DF" },
  sourceTitle: { color: "#182621", fontWeight: "800", fontSize: 15 },
  sourceSnippet: { color: "#33423B", lineHeight: 20, marginTop: 6 },
  receipt: { color: "#1F6F5B", fontWeight: "800", fontSize: 12, marginTop: 8 },
  input: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D7DDD5", borderRadius: 8, padding: 13, fontSize: 16, color: "#182621" },
  tipCard: { backgroundColor: "#EEF3EE", borderRadius: 8, padding: 14, marginTop: 12 },
  empty: { color: "#59645E", marginTop: 20, fontSize: 15 },
  tabBar: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "#FFFFFF",
    borderTopWidth: 1,
    borderColor: "#E4E7DF",
    flexDirection: "row",
    paddingTop: 8,
    paddingBottom: 22
  },
  tab: { flex: 1, alignItems: "center", gap: 3 },
  tabText: { color: "#6C756F", fontSize: 12, fontWeight: "700" },
  tabTextActive: { color: "#1F6F5B" }
});
