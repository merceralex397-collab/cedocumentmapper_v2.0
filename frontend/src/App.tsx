import React, { useState, useEffect, useRef } from "react";
import { 
  FileText, Upload, Download, AlertCircle, CheckCircle2, Eye, Info, Trash2
} from "lucide-react";
import logoImg from "./assets/logo.png";

// Types matching Python Domain Models
interface SourceSpan {
  page_index: number | null;
  line_index: number | null;
  bbox: [number, number, number, number] | null;
}

interface DocumentLine {
  text: string;
  page_index: number;
  line_index: number;
  bbox: [number, number, number, number] | null;
  block_id: string | null;
  confidence: number | null;
}

interface DocumentPage {
  page_index: number;
  width: number | null;
  height: number | null;
  lines: DocumentLine[];
}

interface DocumentModel {
  source_path: string;
  source_type: "pdf" | "docx" | "doc" | "eml" | "msg" | "txt";
  pages: DocumentPage[];
  plain_text: string;
  reader_notes: string[];
}

interface ProviderMatch {
  provider_id: string | null;
  provider_name: string;
  confidence: number;
  matched_terms: string[];
  missing_terms: string[];
  rejected_terms: string[];
}

interface ExtractionIssue {
  field: string | null;
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
}

interface FieldExtraction {
  value: string;
  raw_value: string;
  rule_id: string | null;
  confidence: number | null;
  source_span: SourceSpan | null;
  issues: ExtractionIssue[];
}

interface ExtractedRecord {
  provider: ProviderMatch;
  fields: Record<string, FieldExtraction>;
  issues: ExtractionIssue[];
}

interface ExtractionRule {
  id: string;
  kind: string;
  labels?: string[];
  start_label?: string;
  end_label?: string;
  line_number?: number;
  offset?: number;
  pattern?: string;
  tokens?: string[];
  value?: string;
  absent_value?: string;
  line_start?: number;
  line_end?: number;
}

interface ProviderConfig {
  id: string;
  name: string;
  work_provider: string;
  enabled: boolean;
  priority: number;
  detect: {
    required_phrases: string[];
    optional_phrases: string[];
    negative_phrases: string[];
    minimum_confidence: number;
  };
  field_rules: Record<string, ExtractionRule>;
  engineer_report?: boolean;
  use_current_date_for_inspection_date?: boolean;
  force_postcode_for_inspection_address?: boolean;
}

// Global pywebview API declarations
declare global {
  interface Window {
    pywebview?: {
      api: {
        load_providers(): Promise<ProviderConfig[]>;
        save_providers(providers: ProviderConfig[]): Promise<boolean>;
        import_file(path: string, engineer_report?: boolean): Promise<{
          document: DocumentModel;
          record: ExtractedRecord;
          pdf_base64: string | null;
          pdf_path?: string | null;
        }>;
        import_file_data(name: string, base64_data: string, is_engineer_report?: boolean): Promise<{
          document: DocumentModel;
          record: ExtractedRecord;
          pdf_base64: string | null;
        }>;
        re_run_rule(doc_text: string, file_type: string, lines: any[], rule: ExtractionRule, field_key: string): Promise<FieldExtraction>;
        export_json(fields: Record<string, string>): Promise<{ path: string; folder: string }>;
        export_docx(fields: Record<string, string>): Promise<boolean>;
        extract_images(fields: Record<string, string>): Promise<{
          success: boolean;
          count: number;
          message: string;
          folder?: string;
          paths?: string[];
        }>;
        extract_document_with_provider(doc: DocumentModel, provider_cfg: ProviderConfig): Promise<ExtractedRecord>;
        select_file_dialog(): Promise<string>;
        open_folder(folder_path: string): Promise<boolean>;
      };
    };
  }
}

const FIELD_KEYS = [
  "work_provider", "vrm", "vehicle_model", "claimant_name", "reference",
  "incident_date", "instruction_date", "inspection_date", "inspection_address",
  "accident_circumstances", "vat_status", "mileage", "mileage_unit"
];

const FIELD_LABELS: Record<string, string> = {
  work_provider: "Work Provider",
  vrm: "VRM",
  vehicle_model: "Vehicle Model",
  claimant_name: "Claimant Name",
  reference: "Reference",
  incident_date: "Incident Date",
  instruction_date: "Instruction Date",
  inspection_date: "Inspection Date",
  inspection_address: "Inspection Address",
  accident_circumstances: "Accident Circumstances",
  vat_status: "VAT Status",
  mileage: "Mileage",
  mileage_unit: "Mileage Unit"
};

// Helper to convert base64 to Blob URL
const base64ToBlob = (b64Data: string, contentType = "application/pdf") => {
  const sliceSize = 512;
  const byteCharacters = atob(b64Data);
  const byteArrays = [];
  for (let offset = 0; offset < byteCharacters.length; offset += sliceSize) {
    const slice = byteCharacters.slice(offset, offset + sliceSize);
    const byteNumbers = new Array(slice.length);
    for (let i = 0; i < slice.length; i++) {
      byteNumbers[i] = slice.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    byteArrays.push(byteArray);
  }
  return new Blob(byteArrays, { type: contentType });
};

export default function App() {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [initialProviders, setInitialProviders] = useState<ProviderConfig[]>([]);
  const [activeProvider, setActiveProvider] = useState<ProviderConfig | null>(null);
  
  // Document state
  const [document, setDocument] = useState<DocumentModel | null>(null);
  const [record, setRecord] = useState<ExtractedRecord | null>(null);
  const [overrideFields, setOverrideFields] = useState<Set<string>>(new Set());
  
  // Natively Rendered PDF toggle
  const [viewMode, setViewMode] = useState<"text" | "pdf">("text");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  
  // UI selection
  const [selectedField, setSelectedField] = useState<string>("work_provider");
  const [activeTab, setActiveTab] = useState<"details" | "provider" | "rules">("details");
  const [dragActive, setDragActive] = useState<boolean>(false);
  const dragCounter = useRef<number>(0);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: "info" | "success" | "error"; folder?: string } | null>(null);
  const [expandedConfidence, setExpandedConfidence] = useState<Record<string, boolean>>({});
  
  // Custom Select Dropdown State
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Line elements mapping to scroll into view
  const lineRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const getConfidenceExplanation = (_key: string, fieldVal: FieldExtraction) => {
    const confPercent = Math.round((fieldVal.confidence ?? 1) * 100);
    const ruleId = fieldVal.rule_id || "";
    
    if (confPercent >= 100) {
      return "This field was extracted with 100% confidence using an exact matching rule defined in the active provider preset.";
    }
    
    let explanation = `Confidence is at ${confPercent}% because `;
    
    if (ruleId.startsWith("fallback_")) {
      explanation += "no specific rule was defined in the provider preset for this field. The system fell back to a heuristic extraction method ";
      if (ruleId.includes("pattern")) {
        explanation += "using a generic regular expression search.";
      } else if (ruleId.includes("label")) {
        explanation += "by searching for nearby labels using fuzzy matching.";
      } else if (ruleId.includes("next_line")) {
        explanation += "by looking at the line immediately following a detected label.";
      } else if (ruleId.includes("subject")) {
        explanation += "by looking for reference patterns in the subject line.";
      } else {
        explanation += "to extract the value from the document text.";
      }
    } else if (fieldVal.confidence && fieldVal.confidence < 1.0) {
      explanation += `the provider-specific rule '${ruleId}' was matched via fuzzy similarity rather than an exact match.`;
    } else {
      explanation += "the extraction was based on heuristic rules and may require review.";
    }
    
    if (fieldVal.issues && fieldVal.issues.length > 0) {
      explanation += " Additionally, some validation rules failed: " + fieldVal.issues.map(iss => iss.message).join(" ");
    }
    
    return explanation;
  };

  const handleClearWorkspace = () => {
    setDocument(null);
    setRecord(null);
    setPdfUrl(null);
    setSelectedField("work_provider");
    setOverrideFields(new Set());
    setExpandedConfidence({});
  };

  const handleCreateNewProviderFromTemp = async () => {
    if (!activeProvider) return;
    const name = activeProvider.name.trim();
    const wp = activeProvider.work_provider.trim();
    if (!name || name === "New Provider (Auto-Detected)" || !wp || wp === "UNKNOWN") {
      showStatus("Please enter a valid Provider Name and Work Provider Code first.", "error");
      return;
    }
    
    const newId = name.toLowerCase().replace(/[^a-z0-9]/g, "_");
    
    const field_rules: Record<string, any> = {};
    FIELD_KEYS.forEach(key => {
      if (key === "work_provider") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "manual", value: wp };
      } else if (key === "vrm") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Reg:", "Vehicle Reg:", "Registration:"] };
      } else if (key === "vehicle_model") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Vehicle:", "Model:", "Make/Model:"] };
      } else if (key === "claimant_name") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Client:", "Name:", "Claimant:"] };
      } else if (key === "reference") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Ref:", "Our Ref:", "Reference:"] };
      } else if (key === "incident_date") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Accident Date:", "Incident Date:", "Date of Accident:"] };
      } else if (key === "instruction_date") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Instruction Date:", "Date:"] };
      } else if (key === "inspection_date") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "manual", value: "" };
      } else if (key === "inspection_address") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Address:", "Location:"] };
      } else if (key === "accident_circumstances") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "between_labels", start_label: "Accident Circumstances:", end_label: "Vehicle:" };
      } else if (key === "vat_status") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "presence", tokens: ["VAT Registered: yes", "VAT: Yes"] };
      } else if (key === "mileage") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "label_same_line", labels: ["Mileage:", "Odometer:"] };
      } else if (key === "mileage_unit") {
        field_rules[key] = { id: `${newId}_${key}`, kind: "presence", tokens: ["miles", "km"] };
      }
    });

    const newProvider: ProviderConfig = {
      id: newId,
      name,
      work_provider: wp,
      enabled: true,
      priority: 10,
      detect: {
        required_phrases: activeProvider.detect.required_phrases.length > 0 
          ? activeProvider.detect.required_phrases 
          : [name],
        optional_phrases: [],
        negative_phrases: [],
        minimum_confidence: 0.75
      },
      field_rules
    };

    const updatedProviders = [...providers.filter(p => p.id !== "unknown_temp" && p.id !== newId), newProvider];
    setProviders(updatedProviders);
    setInitialProviders([...initialProviders.filter(p => p.id !== newId), newProvider]);
    setActiveProvider(newProvider);
    
    if (window.pywebview) {
      try {
        const success = await window.pywebview.api.save_providers(updatedProviders);
        if (success) {
          showStatus("Provider preset created and saved successfully!", "success");
          if (document) {
            const newRecord = await window.pywebview.api.extract_document_with_provider(document, newProvider);
            setRecord(newRecord);
          }
        } else {
          showStatus("Failed to save provider to disk.", "error");
        }
      } catch (err) {
        showStatus("Error saving provider: " + err, "error");
      }
    }
  };

  // Prevent default drag and drop behavior on window
  useEffect(() => {
    const preventDefault = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("dragover", preventDefault);
    window.addEventListener("drop", preventDefault);
    return () => {
      window.removeEventListener("dragover", preventDefault);
      window.removeEventListener("drop", preventDefault);
    };
  }, []);

  // PDF Blob URL Cleanup to prevent Windows file locking
  useEffect(() => {
    return () => {
      if (pdfUrl) {
        if (pdfUrl.startsWith("blob:")) {
          URL.revokeObjectURL(pdfUrl);
        }
      }
    };
  }, [pdfUrl]);

  // Load providers safely without concurrent overlapping API calls
  useEffect(() => {
    let intervalId: ReturnType<typeof setTimeout> | null = null;
    let isLoaded = false;

    const fetchProviders = async () => {
      if (isLoaded) return true;
      if (!window.pywebview?.api || typeof window.pywebview.api.load_providers !== "function") return false;
      try {
        const data = await window.pywebview.api.load_providers();
        setProviders(data);
        setInitialProviders(JSON.parse(JSON.stringify(data)));
        if (data.length > 0) {
          setActiveProvider(prev => prev || data[0]);
        }
        isLoaded = true;
        if (intervalId) {
          clearInterval(intervalId);
          intervalId = null;
        }
        return true;
      } catch (err) {
        showStatus("Failed to load providers: " + err, "error");
        isLoaded = true; // stop trying
        if (intervalId) {
          clearInterval(intervalId);
          intervalId = null;
        }
        return true;
      }
    };

    // 1. Try immediately
    fetchProviders();

    // 2. Try on event
    const handleReady = () => {
      fetchProviders();
    };
    window.addEventListener("pywebviewready", handleReady);

    // 3. Fallback poller
    intervalId = setInterval(() => {
      fetchProviders();
    }, 500);

    return () => {
      window.removeEventListener("pywebviewready", handleReady);
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, []);

  // Dropdown outside click handler
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    window.document.addEventListener("mousedown", handleOutsideClick);
    return () => window.document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  // Track provider modified state
  const isProviderModified = (prov: ProviderConfig | null) => {
    if (!prov) return false;
    const initial = initialProviders.find(p => p.id === prov.id);
    if (!initial) return true; // Newly added preset
    return JSON.stringify(prov) !== JSON.stringify(initial);
  };

  const showStatus = (text: string, type: "info" | "success" | "error" = "info", folder?: string) => {
    setStatusMessage({ text, type, folder });
    setTimeout(() => setStatusMessage(null), 5000);
  };

  const handleSelectFile = async (isEngineerReport = false) => {
    if (!window.pywebview?.api) {
      showStatus("Desktop interface not ready.", "error");
      return;
    }
    try {
      const path = await window.pywebview.api.select_file_dialog();
      if (path) {
        showStatus(`Importing ${isEngineerReport ? "Engineer Report" : "Document"}...`, "info");
        const res = await window.pywebview.api.import_file(path, isEngineerReport);
        
        if (isEngineerReport) {
          // Merge values from engineer report
          if (record) {
            const mergedFields = { ...record.fields };
            const newOverrides = new Set(overrideFields);
            
            Object.keys(res.record.fields).forEach(k => {
              const val = res.record.fields[k].value.trim();
              if (val) {
                mergedFields[k] = res.record.fields[k];
                newOverrides.add(k);
              }
            });
            
            setRecord({
              ...record,
              fields: mergedFields,
              issues: [...record.issues, ...res.record.issues]
            });
            setOverrideFields(newOverrides);
            showStatus("Engineer report values overlaid successfully!", "success");
          }
        } else {
          setDocument(res.document);
          setRecord(res.record);
          setOverrideFields(new Set());
          
          // Render native PDF tab if pdf bytes returned
          if (res.pdf_path) {
            setPdfUrl(res.pdf_path);
            setViewMode("pdf");
          } else if (res.pdf_base64) {
            const blob = base64ToBlob(res.pdf_base64, "application/pdf");
            const url = URL.createObjectURL(blob);
            setPdfUrl(url);
            setViewMode("pdf");
          } else {
            setPdfUrl(null);
            setViewMode("text");
          }

          // Match active preset selector to detected provider
          const matched = providers.find(p => p.id === res.record.provider.provider_id);
          if (matched) {
            setActiveProvider(matched);
          } else if (res.record.provider.provider_id === "unknown_temp") {
            const tempProvider: ProviderConfig = {
              id: "unknown_temp",
              name: "New Provider (Auto-Detected)",
              work_provider: "UNKNOWN",
              enabled: true,
              priority: 999,
              detect: {
                required_phrases: [],
                optional_phrases: [],
                negative_phrases: [],
                minimum_confidence: 0.0
              },
              field_rules: {}
            };
            setActiveProvider(tempProvider);
          }
          showStatus("Document parsed successfully!", "success");
        }
      }
    } catch (err) {
      showStatus("Import failed: " + err, "error");
    }
  };

  // Drag and Drop
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter") {
      dragCounter.current++;
      if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
        setDragActive(true);
      }
    } else if (e.type === "dragover") {
      e.preventDefault();
      setDragActive(true);
    } else if (e.type === "dragleave") {
      dragCounter.current--;
      if (dragCounter.current <= 0) {
        setDragActive(false);
      }
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    dragCounter.current = 0;
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      
      // Instantly generate native PDF Object URL locally for perfect performance
      if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
        const url = URL.createObjectURL(file);
        setPdfUrl(url);
      } else {
        setPdfUrl(null);
      }

      const reader = new FileReader();
      reader.onload = async (event) => {
        const result = event.target?.result as string;
        if (!result) return;
        const base64Data = result.split(",")[1];
        
        if (window.pywebview?.api) {
          showStatus("Parsing dropped document...", "info");
          try {
            const res = await window.pywebview.api.import_file_data(file.name, base64Data, false);
            setDocument(res.document);
            setRecord(res.record);
            setOverrideFields(new Set());
            
            // If PDF, use native rendering tab
            if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
              setViewMode("pdf");
            } else {
              setViewMode("text");
            }

            const matched = providers.find(p => p.id === res.record.provider.provider_id);
            if (matched) {
              setActiveProvider(matched);
            }
            showStatus("Document parsed successfully!", "success");
          } catch (err) {
            showStatus("Import failed: " + err, "error");
          }
        } else {
          showStatus("Desktop interface not ready.", "error");
        }
      };
      
      reader.onerror = () => {
        showStatus("Failed to read dropped file.", "error");
      };
      
      reader.readAsDataURL(file);
    }
  };

  // Trigger live rule sandbox re-run
  const triggerLiveSandbox = async (updatedRule: ExtractionRule) => {
    if (!document || !window.pywebview?.api) return;
    try {
      const flatLines = document.pages.flatMap(p => p.lines);
      const ext = await window.pywebview.api.re_run_rule(
        document.plain_text,
        document.source_type,
        flatLines,
        updatedRule,
        selectedField
      );
      
      if (record) {
        const updatedFields = { ...record.fields, [selectedField]: ext };
        setRecord({ ...record, fields: updatedFields });
      }
    } catch (err) {
      console.error("Live run failed:", err);
    }
  };

  const handleRuleChange = (key: keyof ExtractionRule, val: any) => {
    if (!activeProvider) return;
    const currentRule = activeProvider.field_rules[selectedField] || { id: `${activeProvider.id}_${selectedField}`, kind: "label_same_line" };
    const updatedRule = { ...currentRule, [key]: val };
    
    const updatedProvider = {
      ...activeProvider,
      field_rules: {
        ...activeProvider.field_rules,
        [selectedField]: updatedRule
      }
    };
    
    setActiveProvider(updatedProvider);
    setProviders(providers.map(p => p.id === activeProvider.id ? updatedProvider : p));
    triggerLiveSandbox(updatedRule);
  };

  // Provider Metadata Edit handlers
  const handleProviderMetaChange = (key: string, val: any) => {
    if (!activeProvider) return;
    let updated: ProviderConfig;
    if (key === "required_phrases") {
      updated = {
        ...activeProvider,
        detect: {
          ...activeProvider.detect,
          required_phrases: val
        }
      };
    } else {
      updated = {
        ...activeProvider,
        [key]: val
      };
    }
    setActiveProvider(updated);
    setProviders(providers.map(p => p.id === activeProvider.id ? updated : p));
  };

  const handleAddNewProvider = () => {
    const newId = `preset_${Date.now()}`;
    const newProvider: ProviderConfig = {
      id: newId,
      name: "New Provider Preset",
      work_provider: "NEW",
      enabled: true,
      priority: 0,
      detect: {
        required_phrases: ["New Unique Phrase"],
        optional_phrases: [],
        negative_phrases: [],
        minimum_confidence: 0.75
      },
      field_rules: {}
    };
    const updated = [...providers, newProvider];
    setProviders(updated);
    setActiveProvider(newProvider);
    showStatus("New preset created! Modify settings and click Save All Presets.", "success");
  };

  const handleResetProvider = () => {
    if (!activeProvider) return;
    const initial = initialProviders.find(p => p.id === activeProvider.id);
    if (initial) {
      const restored = JSON.parse(JSON.stringify(initial));
      setActiveProvider(restored);
      setProviders(providers.map(p => p.id === activeProvider.id ? restored : p));
      showStatus("Preset reset to default values.", "info");
    } else {
      const updated = providers.filter(p => p.id !== activeProvider.id);
      setProviders(updated);
      setActiveProvider(updated[0] || null);
      showStatus("Unsaved preset discarded.", "info");
    }
  };

  const handleResetFieldRule = (fieldKey: string) => {
    if (!activeProvider) return;
    const initial = initialProviders.find(p => p.id === activeProvider.id);
    if (!initial) return;
    const initialRule = initial.field_rules[fieldKey];
    if (initialRule) {
      const restoredRule = JSON.parse(JSON.stringify(initialRule));
      const updatedProvider = {
        ...activeProvider,
        field_rules: {
          ...activeProvider.field_rules,
          [fieldKey]: restoredRule
        }
      };
      setActiveProvider(updatedProvider);
      setProviders(providers.map(p => p.id === activeProvider.id ? updatedProvider : p));
      showStatus(`Field rule for ${FIELD_LABELS[fieldKey]} reset to default.`, "info");
      
      // Optionally trigger live sandbox with restored rule
      triggerLiveSandbox(restoredRule);
    }
  };

  const getRuleSummary = (rule: any) => {
    if (!rule) return "";
    switch (rule.kind) {
      case "label_same_line":
      case "label_same_or_next_line":
      case "label_next_line":
      case "email_date":
        return `(labels: ${(rule.labels || []).join(", ")})`;
      case "between_labels":
        return `(between "${rule.start_label || ''}" and "${rule.end_label || ''}")`;
      case "fixed_line":
        return rule.line_start && rule.line_end
          ? `(lines: ${rule.line_start}-${rule.line_end})`
          : `(line: ${rule.line_number || 1})`;
      case "fixed_line_label":
        return `(line: ${rule.line_number || 1}, labels: ${(rule.labels || []).join(", ")})`;
      case "line_offset":
        return `(offset: ${rule.offset >= 0 ? '+' : ''}${rule.offset}, labels: ${(rule.labels || []).join(", ")})`;
      case "regex":
        return `(pattern: "${rule.pattern || ''}")`;
      case "presence":
        return `(tokens: ${(rule.tokens || []).join(", ")}, value: "${rule.value || ''}", absent: "${rule.absent_value || ''}")`;
      case "manual":
        return `(value: "${rule.value || ''}")`;
      default:
        return "";
    }
  };

  const handleDeleteProvider = () => {
    if (!activeProvider || providers.length <= 1) return;
    if (window.confirm(`Are you sure you want to delete the preset "${activeProvider.name}"?`)) {
      const updated = providers.filter(p => p.id !== activeProvider.id);
      setProviders(updated);
      setActiveProvider(updated[0]);
      showStatus("Preset removed locally. Click Save to commit change.", "info");
    }
  };

  const handleFieldValueChange = (val: string) => {
    if (!record) return;
    const currentField = record.fields[selectedField] || { value: "", raw_value: "" };
    const updatedFields = {
      ...record.fields,
      [selectedField]: { ...currentField, value: val }
    };
    setRecord({ ...record, fields: updatedFields });
  };

  const handleSaveProviders = async () => {
    if (!window.pywebview?.api) return;
    try {
      const ok = await window.pywebview.api.save_providers(providers);
      if (ok) {
        setInitialProviders(JSON.parse(JSON.stringify(providers)));
        showStatus("All presets successfully saved to disk!", "success");
      }
    } catch (err) {
      showStatus("Save presets failed: " + err, "error");
    }
  };

  const handleExportJSON = async () => {
    if (!record || !window.pywebview?.api) return;
    try {
      const fieldsMap: Record<string, string> = {};
      Object.keys(record.fields).forEach(k => {
        fieldsMap[k] = record.fields[k].value;
      });
      const result = await window.pywebview.api.export_json(fieldsMap);
      if (result.path) {
        showStatus("JSON exported. Open output folder.", "success", result.folder);
      }
    } catch (err) {
      showStatus("JSON Export failed: " + err, "error");
    }
  };

  const handleExportDOCX = async () => {
    if (!record || !window.pywebview?.api) return;
    try {
      const fieldsMap: Record<string, string> = {};
      Object.keys(record.fields).forEach(k => {
        fieldsMap[k] = record.fields[k].value;
      });
      const ok = await window.pywebview.api.export_docx(fieldsMap);
      if (ok) {
        showStatus("RJS Letter exported to Desktop successfully!", "success");
      }
    } catch (err) {
      showStatus("DOCX Export failed: " + err, "error");
    }
  };

  const handleExtractImages = async () => {
    if (!record || !window.pywebview?.api) return;
    try {
      const fieldsMap: Record<string, string> = {};
      Object.keys(record.fields).forEach(k => {
        fieldsMap[k] = record.fields[k].value;
      });
      showStatus("Extracting images to Desktop...", "info");
      const res = await window.pywebview.api.extract_images(fieldsMap);
      if (res.success) {
        showStatus(res.message + " Open output folder.", "success", res.folder);
      } else {
        showStatus(res.message, "error");
      }
    } catch (err) {
      showStatus("Image extraction failed: " + err, "error");
    }
  };

  const handleProviderChange = async (provider: ProviderConfig) => {
    setActiveProvider(provider);
    if (document && window.pywebview?.api) {
      try {
        showStatus("Re-extracting fields...", "info");
        const newRecord = await window.pywebview.api.extract_document_with_provider(document, provider);
        setRecord(newRecord);
        setOverrideFields(new Set());
        showStatus(`Fields updated using preset: ${provider.name}`, "success");
      } catch (err) {
        showStatus("Re-extraction failed: " + err, "error");
      }
    }
  };

  // Scroll matching source span line into view
  const handleFieldClick = (key: string) => {
    setSelectedField(key);
    const fieldData = record?.fields[key];
    if (fieldData?.source_span) {
      const span = fieldData.source_span;
      const elementId = `line-${span.page_index}-${span.line_index}`;
      const el = lineRefs.current[elementId];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  };

  return (
    <div 
      className="app-container"
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      {/* Top Header & Preset Bar */}
      <div className="panel top-bar">
        <div style={{ display: "flex", alignItems: "center", gap: "28px" }}>
          <h1 style={{ display: "flex", alignItems: "center", gap: "10px", background: "none", WebkitBackgroundClip: "initial", WebkitTextFillColor: "initial", color: "var(--text-primary)" }}>
            <img src={logoImg} alt="CE Logo" style={{ height: "24px", width: "auto" }} />
            CE Document Mapper v2.0
          </h1>
          
          {/* Custom Dropdown Component */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px", position: "relative" }} ref={dropdownRef}>
            <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Active Preset:
            </span>
            <div className="custom-select-container">
              <div 
                className="custom-select-trigger"
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                style={{ borderColor: isProviderModified(activeProvider) ? "var(--warning)" : "var(--border-color)" }}
              >
                <span>
                  {activeProvider ? `${activeProvider.name} (${activeProvider.work_provider})` : "No Presets"}
                  {isProviderModified(activeProvider) && <span style={{ color: "var(--warning)", marginLeft: "6px", fontSize: "11px" }}>● Modified</span>}
                </span>
                <span style={{ fontSize: "9px", transition: "transform 0.2s", transform: isDropdownOpen ? "rotate(180deg)" : "rotate(0)" }}>▼</span>
              </div>
              {isDropdownOpen && (
                <div className="custom-select-options">
                  {providers.map(p => (
                    <div 
                      key={p.id} 
                      className={`custom-select-option ${activeProvider?.id === p.id ? "selected" : ""}`}
                      onClick={() => {
                        handleProviderChange(p);
                        setIsDropdownOpen(false);
                      }}
                    >
                      <span>{p.name} ({p.work_provider})</span>
                      {isProviderModified(p) && <span style={{ color: "var(--warning)", marginLeft: "auto", fontSize: "10px" }}>● Modified</span>}
                    </div>
                  ))}
                  {providers.length === 0 && (
                    <div style={{ padding: "8px 12px", color: "var(--text-muted)", fontSize: "12px", fontStyle: "italic" }}>
                      No presets found
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button className="btn" onClick={() => handleSelectFile(false)}>
            <Upload size={14} /> Import Instruction
          </button>
          {document && (
            <button className="btn" onClick={handleClearWorkspace} style={{ borderColor: "rgba(239, 68, 68, 0.4)", color: "#fca5a5" }}>
              <Trash2 size={14} /> Clear Workspace
            </button>
          )}
          <button className="btn" onClick={() => handleSelectFile(true)} disabled={!document}>
            <Eye size={14} /> Overlay Eng Report
          </button>
          <button className="btn btn-primary" onClick={handleExportJSON} disabled={!record}>
            <Download size={14} /> Export JSON
          </button>
          {activeProvider?.id === "rjs" && (
            <button className="btn btn-primary" onClick={handleExportDOCX} disabled={!record}>
              <FileText size={14} /> Export RJS DOCX
            </button>
          )}
          <button className="btn" onClick={handleExtractImages} disabled={!document}>
            <Download size={14} /> Extract Images
          </button>
        </div>
      </div>

      {/* Main Workspace Grid */}
      <div className="main-content">
        
        {/* Left Panel: Fields List & Validation */}
        <div className="panel">
          <h2>Detected Fields</h2>
          <div className="field-list">
            {FIELD_KEYS.map(key => {
              const fieldVal = record?.fields[key];
              const valText = fieldVal?.value || "";
              const hasOverride = overrideFields.has(key);
              
              // Validate empty status
              let statusClass = "valid";
              if (valText.trim() === "") {
                statusClass = ["work_provider", "vrm", "vehicle_model", "claimant_name", "reference", "incident_date", "instruction_date"].includes(key)
                  ? "required-empty"
                  : "warning";
              }

              return (
                <div 
                  key={key} 
                  className={`field-item ${selectedField === key ? "active" : ""}`}
                  onClick={() => handleFieldClick(key)}
                >
                  <div className="field-header">
                    <div style={{ display: "flex", alignItems: "center" }}>
                      <span className="field-label">{FIELD_LABELS[key]}</span>
                      {hasOverride && <span className="field-override-badge">Engineer Overlaid</span>}
                    </div>
                    <span className={`field-status ${statusClass}`} />
                  </div>
                  <div className={`field-value ${valText ? "" : "empty"}`}>
                    {valText || "Not extracted"}
                  </div>
                  {fieldVal && (
                    <div style={{ marginTop: "6px", fontSize: "10px", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "4px" }}>
                      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                        {typeof fieldVal.confidence === "number" && (
                          <span style={fieldVal.confidence < 1.0 ? { color: "var(--warning)", display: "inline-flex", alignItems: "center", gap: "4px" } : {}}>
                            {Math.round(fieldVal.confidence * 100)}% confidence
                            {fieldVal.confidence < 1.0 && (
                              <button 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedConfidence(prev => ({ ...prev, [key]: !prev[key] }));
                                }}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--warning)", padding: 0, display: "inline-flex", alignItems: "center" }}
                              >
                                <Info size={12} />
                              </button>
                            )}
                          </span>
                        )}
                        {fieldVal.rule_id && <span>{fieldVal.rule_id}</span>}
                        {fieldVal.source_span && <span>p{(fieldVal.source_span.page_index ?? 0) + 1}:l{(fieldVal.source_span.line_index ?? 0) + 1}</span>}
                        {fieldVal.issues.length > 0 && <span>{fieldVal.issues.length} issue{fieldVal.issues.length === 1 ? "" : "s"}</span>}
                      </div>
                      {expandedConfidence[key] && (
                        <div 
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            marginTop: "4px",
                            padding: "6px 8px",
                            backgroundColor: "rgba(245, 158, 11, 0.08)",
                            border: "1px solid rgba(245, 158, 11, 0.2)",
                            borderRadius: "4px",
                            color: "#f59e0b",
                            lineHeight: "1.3"
                          }}
                        >
                          {getConfidenceExplanation(key, fieldVal)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          
          {/* Validation issues list */}
          {record && record.issues.length > 0 && (
            <div className="issues-panel">
              <div style={{ fontSize: "11px", fontWeight: "bold", marginBottom: "8px", textTransform: "uppercase" }}>
                Validation Messages ({record.issues.length})
              </div>
              {record.issues.map((iss, i) => (
                <div key={i} className={`issue-card ${iss.severity}`}>
                  <AlertCircle size={14} style={{ flexShrink: 0 }} />
                  <div>{iss.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Middle Panel: Visual Document Preview (with Tab Switcher) */}
        <div className="panel preview-container">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingRight: "16px" }}>
            <h2>
              <FileText size={16} />
              Source Preview
              {document && (
                <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: "normal" }}>
                  ({document.source_type.toUpperCase()} - {document.pages.length} Pages)
                </span>
              )}
            </h2>
            {pdfUrl && (
              <div style={{ display: "flex", gap: "4px", background: "rgba(0,0,0,0.2)", padding: "2px", borderRadius: "6px" }}>
                <button 
                  className={`btn ${viewMode === "text" ? "btn-primary" : ""}`}
                  style={{ height: "26px", padding: "0 10px", fontSize: "11px", borderRadius: "4px", border: "none", boxShadow: "none" }}
                  onClick={() => setViewMode("text")}
                >
                  Text View
                </button>
                <button 
                  className={`btn ${viewMode === "pdf" ? "btn-primary" : ""}`}
                  style={{ height: "26px", padding: "0 10px", fontSize: "11px", borderRadius: "4px", border: "none", boxShadow: "none" }}
                  onClick={() => setViewMode("pdf")}
                >
                  {document?.source_type === "pdf" 
                    ? "Natively Rendered PDF" 
                    : (document?.source_type === "eml" || document?.source_type === "msg") 
                      ? "Natively Rendered Email" 
                      : "Natively Rendered Document"}
                </button>
              </div>
            )}
          </div>
          
          <div className="preview-content" style={{ padding: viewMode === "pdf" && pdfUrl ? 0 : "24px" }}>
            {document ? (
              viewMode === "pdf" && pdfUrl ? (
                <iframe 
                  src={pdfUrl} 
                  style={{ width: "100%", height: "100%", border: "none", borderRadius: "0 0 12px 12px" }}
                  title={document?.source_type === "pdf" 
                    ? "Natively Rendered PDF Viewer" 
                    : (document?.source_type === "eml" || document?.source_type === "msg") 
                      ? "Natively Rendered Email Viewer" 
                      : "Natively Rendered Document Viewer"}
                />
              ) : (
                document.pages.map(page => (
                  <div key={page.page_index} className="preview-page">
                    <div style={{ position: "absolute", top: "10px", right: "16px", fontSize: "10px", color: "var(--text-muted)" }}>
                      PAGE {page.page_index + 1}
                    </div>
                    {page.lines.map(line => {
                      const elKey = `line-${line.page_index}-${line.line_index}`;
                      
                      // Highlight if this line matches any field
                      let matchedField = false;
                      let isActiveFieldMatch = false;
                      
                      if (record) {
                        Object.keys(record.fields).forEach(k => {
                          const span = record.fields[k].source_span;
                          if (span && span.page_index === line.page_index && span.line_index === line.line_index) {
                            matchedField = true;
                            if (selectedField === k) {
                              isActiveFieldMatch = true;
                            }
                          }
                        });
                      }

                      return (
                        <div
                          key={line.line_index}
                          ref={el => { lineRefs.current[elKey] = el; }}
                          className={`preview-line ${matchedField ? "matched" : ""} ${isActiveFieldMatch ? "active" : ""}`}
                          style={{ minHeight: "18px" }}
                        >
                          {line.text}
                        </div>
                      );
                    })}
                  </div>
                ))
              )
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "12px" }}>
                <Upload size={48} style={{ color: "var(--text-muted)" }} />
                <div style={{ fontSize: "14px", color: "var(--text-secondary)" }}>Drag and drop claim instruction document here</div>
                <button className="btn btn-primary" onClick={() => handleSelectFile(false)}>Choose File</button>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Settings / Live Rule Sandbox */}
        <div className="panel">
          <div className="tabs">
            <div className={`tab ${activeTab === "details" ? "active" : ""}`} onClick={() => setActiveTab("details")}>
              Value Override
            </div>
            <div className={`tab ${activeTab === "provider" ? "active" : ""}`} onClick={() => setActiveTab("provider")}>
              Provider Settings
            </div>
            <div className={`tab ${activeTab === "rules" ? "active" : ""}`} onClick={() => setActiveTab("rules")}>
              Extraction Rules
            </div>
          </div>

          {activeProvider?.id === "unknown_temp" && (
            <div style={{
              margin: "12px 16px 4px 16px",
              padding: "10px 12px",
              backgroundColor: "rgba(239, 68, 68, 0.08)",
              border: "1px solid rgba(239, 68, 68, 0.25)",
              borderRadius: "6px",
              color: "#f87171",
              fontSize: "12px",
              lineHeight: "1.4"
            }}>
              <div style={{ fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                <AlertCircle size={14} /> New Provider Detected
              </div>
              Review these auto-extracted fields and save them as a new provider preset under Provider Settings.
            </div>
          )}

          {activeTab === "details" && (
            <div style={{ padding: "16px", overflowY: "auto", flexGrow: 1 }}>
              <div style={{ marginBottom: "16px", fontSize: "13px", color: "var(--text-secondary)" }}>
                Directly edit the value for <span style={{ color: "white", fontWeight: "bold" }}>{FIELD_LABELS[selectedField]}</span> below.
              </div>
              <div className="form-group" style={{ padding: 0 }}>
                {selectedField === "inspection_address" ? (
                  <textarea 
                    rows={8}
                    value={record?.fields[selectedField]?.value || ""}
                    onChange={(e) => handleFieldValueChange(e.target.value)}
                  />
                ) : (
                  <input 
                    type="text"
                    value={record?.fields[selectedField]?.value || ""}
                    onChange={(e) => handleFieldValueChange(e.target.value)}
                  />
                )}
              </div>
            </div>
          )}

          {activeTab === "provider" && (
            <div style={{ padding: "16px", overflowY: "auto", flexGrow: 1, display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "8px" }}>
                Edit global preset properties for the active provider. Providers define how fields are mapped and extracted.
              </div>
              
              <div className="form-group" style={{ padding: 0 }}>
                <label>Provider Name</label>
                <input 
                  type="text"
                  value={activeProvider?.name || ""}
                  onChange={(e) => handleProviderMetaChange("name", e.target.value)}
                />
              </div>

              <div className="form-group" style={{ padding: 0 }}>
                <label>Work Provider Code</label>
                <input 
                  type="text"
                  value={activeProvider?.work_provider || ""}
                  onChange={(e) => handleProviderMetaChange("work_provider", e.target.value)}
                />
              </div>

              <div className="form-group" style={{ padding: 0 }}>
                <label>Detect Phrases (one per line)</label>
                <textarea 
                  rows={4}
                  value={(activeProvider?.detect?.required_phrases || []).join("\n")}
                  onChange={(e) => handleProviderMetaChange("required_phrases", e.target.value.split("\n").map(l => l.trim()).filter(Boolean))}
                  placeholder="Phrases that must appear in the document text"
                />
              </div>

              <div className="form-group" style={{ padding: 0, flexDirection: "row", alignItems: "center", gap: "10px", marginTop: "8px" }}>
                <input 
                  type="checkbox"
                  id="chk-eng-report"
                  style={{ width: "auto" }}
                  checked={activeProvider?.engineer_report || false}
                  onChange={(e) => handleProviderMetaChange("engineer_report", e.target.checked)}
                />
                <label htmlFor="chk-eng-report" style={{ cursor: "pointer", fontSize: "12px" }}>Is Engineer Report (Overlay Source)</label>
              </div>

              <div className="form-group" style={{ padding: 0, flexDirection: "row", alignItems: "center", gap: "10px" }}>
                <input 
                  type="checkbox"
                  id="chk-curr-date"
                  style={{ width: "auto" }}
                  checked={activeProvider?.use_current_date_for_inspection_date || false}
                  onChange={(e) => handleProviderMetaChange("use_current_date_for_inspection_date", e.target.checked)}
                />
                <label htmlFor="chk-curr-date" style={{ cursor: "pointer", fontSize: "12px" }}>Use Current Date for Inspection Date</label>
              </div>

              <div className="form-group" style={{ padding: 0, flexDirection: "row", alignItems: "center", gap: "10px" }}>
                <input 
                  type="checkbox"
                  id="chk-postcode"
                  style={{ width: "auto" }}
                  checked={activeProvider?.force_postcode_for_inspection_address || false}
                  onChange={(e) => handleProviderMetaChange("force_postcode_for_inspection_address", e.target.checked)}
                />
                <label htmlFor="chk-postcode" style={{ cursor: "pointer", fontSize: "12px" }}>Force Postcode for Inspection Address</label>
              </div>

              {activeProvider?.id === "unknown_temp" ? (
                <button 
                  className="btn btn-primary" 
                  style={{ marginTop: "24px", alignSelf: "stretch", justifyContent: "center", backgroundColor: "var(--accent-teal)", borderColor: "var(--accent-teal)" }}
                  onClick={handleCreateNewProviderFromTemp}
                >
                  Create and Save Preset
                </button>
              ) : (
                <>
                  <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
                    <button className="btn" style={{ flexGrow: 1, fontSize: "12px", padding: "6px" }} onClick={handleAddNewProvider}>
                      Add Preset
                    </button>
                    <button className="btn" style={{ flexGrow: 1, fontSize: "12px", padding: "6px" }} onClick={handleResetProvider} disabled={!isProviderModified(activeProvider)}>
                      Reset Preset
                    </button>
                    <button className="btn" style={{ flexGrow: 1, fontSize: "12px", padding: "6px", color: "var(--error)" }} onClick={handleDeleteProvider} disabled={providers.length <= 1}>
                      Delete Preset
                    </button>
                  </div>

                  <button 
                    className="btn btn-primary" 
                    style={{ marginTop: "24px", alignSelf: "stretch", justifyContent: "center" }}
                    onClick={handleSaveProviders}
                  >
                    Save All Presets to Disk
                  </button>
                </>
              )}
            </div>
          )}

          {activeTab === "rules" && (
            <div style={{ padding: "16px", overflowY: "auto", flexGrow: 1, display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "8px" }}>
                Configure mapping and extraction rules for each field on preset <span style={{ color: "white", fontWeight: "bold" }}>{activeProvider?.name}</span>.
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {FIELD_KEYS.map(key => {
                  const rule = activeProvider?.field_rules[key] || { id: `${activeProvider?.id}_${key}`, kind: "label_same_line" };
                  const initialRule = initialProviders.find(p => p.id === activeProvider?.id)?.field_rules[key];
                  const isRuleModified = JSON.stringify(rule) !== JSON.stringify(initialRule);
                  const isExpanded = selectedField === key;

                  return (
                    <div 
                      key={key} 
                      className={`rule-field-item ${isExpanded ? "expanded" : ""}`}
                      style={{
                        border: "1px solid var(--border-color)",
                        borderRadius: "8px",
                        background: isExpanded ? "rgba(255,255,255,0.02)" : "transparent",
                        overflow: "hidden"
                      }}
                    >
                      <div 
                        onClick={() => handleFieldClick(key)}
                        style={{
                          padding: "10px 12px",
                          cursor: "pointer",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          background: isExpanded ? "rgba(225, 29, 72, 0.05)" : "transparent"
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{ fontSize: "12px", fontWeight: "600", color: isExpanded ? "var(--accent-teal)" : "var(--text-primary)" }}>
                            {FIELD_LABELS[key]}
                          </span>
                          {isRuleModified && (
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <span className="field-override-badge" style={{ background: "var(--warning)" }}>
                                Modified
                              </span>
                              <span 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleResetFieldRule(key);
                                }}
                                style={{ 
                                  color: "var(--accent-teal)", 
                                  fontSize: "11px", 
                                  textDecoration: "underline", 
                                  fontWeight: "500",
                                  cursor: "pointer"
                                }}
                              >
                                Reset
                              </span>
                            </div>
                          )}
                        </div>
                        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                          {rule ? rule.kind.replace(/_/g, " ") : "Not configured"} {isExpanded ? "▲" : "▼"}
                        </span>
                      </div>

                      {/* Accordion Editor Panel */}
                      {isExpanded && (
                        <div style={{ padding: "12px", borderTop: "1px solid var(--border-color)", display: "flex", flexDirection: "column", gap: "10px" }}>
                          {/* Rule Editor */}
                          <div className="form-group" style={{ padding: 0 }}>
                            <label>Rule Type</label>
                            <select 
                              value={rule?.kind || "label_same_line"}
                              onChange={(e) => handleRuleChange("kind", e.target.value)}
                            >
                              <option value="label_same_or_next_line">Single Label (Same Line/Next Line)</option>
                              <option value="label_same_line">Label (Same Line Only)</option>
                              <option value="label_next_line">Label (Next Line Only)</option>
                              <option value="between_labels">Between Labels</option>
                              <option value="fixed_line">Fixed Line Position</option>
                              <option value="fixed_line_label">Fixed Line + Label</option>
                              <option value="line_offset">Label +/- Line Offset</option>
                              <option value="regex">Regex Pattern</option>
                              <option value="presence">Token Presence Check</option>
                              <option value="manual">Manual Input Literal</option>
                              <option value="email_date">Email Header Date</option>
                            </select>
                          </div>

                          {/* Dynamic rule fields depending on rule type */}
                          {["label_same_line", "label_same_or_next_line", "label_next_line", "fixed_line_label", "line_offset", "email_date"].includes(rule?.kind || "") && (
                            <div className="form-group" style={{ padding: 0 }}>
                              <label>Label Strings (comma-separated)</label>
                              <input 
                                type="text"
                                value={(rule?.labels || []).join(", ")}
                                onChange={(e) => handleRuleChange("labels", e.target.value.split(",").map(t => t.trim()))}
                                placeholder="e.g. Reference:, Our Ref:"
                              />
                            </div>
                          )}

                          {rule?.kind === "between_labels" && (
                            <>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>Start Label</label>
                                <input 
                                  type="text"
                                  value={rule?.start_label || ""}
                                  onChange={(e) => handleRuleChange("start_label", e.target.value)}
                                />
                              </div>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>End Label</label>
                                <input 
                                  type="text"
                                  value={rule?.end_label || ""}
                                  onChange={(e) => handleRuleChange("end_label", e.target.value)}
                                />
                              </div>
                            </>
                          )}

                          {["fixed_line", "fixed_line_label"].includes(rule?.kind || "") && (
                            <>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>Line Number (1-based)</label>
                                <input 
                                  type="number"
                                  value={rule?.line_number || 1}
                                  onChange={(e) => handleRuleChange("line_number", parseInt(e.target.value) || 1)}
                                />
                              </div>
                              {rule?.kind === "fixed_line" && (
                                <div className="form-group" style={{ padding: 0 }}>
                                  <label>Optional Line Range</label>
                                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                                    <input
                                      type="number"
                                      value={rule?.line_start || ""}
                                      onChange={(e) => handleRuleChange("line_start", e.target.value ? parseInt(e.target.value) : undefined)}
                                      placeholder="Start"
                                    />
                                    <input
                                      type="number"
                                      value={rule?.line_end || ""}
                                      onChange={(e) => handleRuleChange("line_end", e.target.value ? parseInt(e.target.value) : undefined)}
                                      placeholder="End"
                                    />
                                  </div>
                                </div>
                              )}
                            </>
                          )}

                          {rule?.kind === "line_offset" && (
                            <div className="form-group" style={{ padding: 0 }}>
                              <label>Line Offset (e.g. +1, -2)</label>
                              <input 
                                type="number"
                                value={rule?.offset || 0}
                                onChange={(e) => handleRuleChange("offset", parseInt(e.target.value) || 0)}
                              />
                            </div>
                          )}

                          {rule?.kind === "regex" && (
                            <div className="form-group" style={{ padding: 0 }}>
                              <label>Regex Pattern</label>
                              <input 
                                type="text"
                                value={rule?.pattern || ""}
                                onChange={(e) => handleRuleChange("pattern", e.target.value)}
                                placeholder="e.g. REF-\d+-[A-Z]+"
                              />
                            </div>
                          )}

                          {rule?.kind === "presence" && (
                            <>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>Keywords/Tokens (comma-separated)</label>
                                <input 
                                  type="text"
                                  value={(rule?.tokens || []).join(", ")}
                                  onChange={(e) => handleRuleChange("tokens", e.target.value.split(",").map(t => t.trim()))}
                                  placeholder="e.g. VAT registered, VAT registration"
                                />
                              </div>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>Value if Present</label>
                                <input 
                                  type="text"
                                  value={rule?.value || "Yes"}
                                  onChange={(e) => handleRuleChange("value", e.target.value)}
                                />
                              </div>
                              <div className="form-group" style={{ padding: 0 }}>
                                <label>Value if Absent</label>
                                <input 
                                  type="text"
                                  value={rule?.absent_value || ""}
                                  onChange={(e) => handleRuleChange("absent_value", e.target.value)}
                                  placeholder="e.g. No, Miles, Km"
                                />
                              </div>
                            </>
                          )}

                          {rule?.kind === "manual" && (
                            <div className="form-group" style={{ padding: 0 }}>
                              <label>Manual Value (use {`{today}`} for current date)</label>
                              <input 
                                type="text"
                                value={rule?.value || ""}
                                onChange={(e) => handleRuleChange("value", e.target.value)}
                              />
                            </div>
                          )}

                          {initialRule && isRuleModified && (
                            <div style={{ 
                              fontSize: "11px", 
                              color: "var(--text-secondary)", 
                              marginTop: "4px", 
                              marginBottom: "8px",
                              padding: "8px 12px", 
                              background: "rgba(251, 191, 36, 0.05)", 
                              border: "1px solid rgba(251, 191, 36, 0.15)",
                              borderRadius: "6px" 
                            }}>
                              <strong style={{ color: "var(--warning)" }}>Initial default config:</strong>
                              <div style={{ marginTop: "3px", fontFamily: "monospace", color: "var(--text-muted)" }}>
                                Type: {initialRule.kind.replace(/_/g, " ")} {getRuleSummary(initialRule)}
                              </div>
                            </div>
                          )}

                          {/* Live Sandbox outputs display */}
                          <div style={{ marginTop: "8px", borderTop: "1px solid var(--border-color)", paddingTop: "12px" }}>
                            <div style={{ fontSize: "10px", fontWeight: "bold", textTransform: "uppercase", marginBottom: "6px", color: "var(--text-muted)" }}>
                              Live Sandbox Test
                            </div>
                            <div style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "10px", minHeight: "44px", fontFamily: "Courier New, Courier, monospace", fontSize: "12px" }}>
                              {record?.fields[key]?.value ? (
                                <div>
                                  <div style={{ color: "var(--success)", fontWeight: "bold", marginBottom: "2px", fontSize: "10px" }}>Success (conf: {record.fields[key].confidence ?? 1.0})</div>
                                  <div style={{ color: "white" }}>{record.fields[key].value}</div>
                                </div>
                              ) : (
                                <div style={{ color: "var(--text-muted)", fontSize: "11px" }}>No match extracted. Update rules to test in real-time.</div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Config Save and Reset buttons */}
              {activeProvider?.id !== "unknown_temp" && (
                <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
                  <button 
                    className="btn"
                    style={{ flexGrow: 1, fontSize: "12px", padding: "6px", justifyContent: "center" }}
                    onClick={handleResetProvider}
                    disabled={!isProviderModified(activeProvider)}
                  >
                    Reset Preset
                  </button>
                  <button 
                    className="btn btn-primary" 
                    style={{ flexGrow: 2, justifyContent: "center" }}
                    onClick={handleSaveProviders}
                  >
                    Save All Presets
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Floating Status Notification */}
      {statusMessage && (
        <div style={{
          position: "fixed",
          bottom: "24px",
          left: "24px",
          background: statusMessage.type === "error" ? "var(--error)" : statusMessage.type === "success" ? "var(--success)" : "var(--accent-teal)",
          color: "white",
          padding: "12px 24px",
          borderRadius: "8px",
          boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          zIndex: 1000,
          fontSize: "14px",
          fontWeight: "500",
          animation: "float 0.3s ease-out"
        }}>
          {statusMessage.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{statusMessage.text}</span>
          {statusMessage.folder && window.pywebview?.api && (
            <button
              className="btn"
              style={{ height: "26px", padding: "0 10px", background: "rgba(255,255,255,0.18)", color: "white", borderColor: "rgba(255,255,255,0.35)" }}
              onClick={() => window.pywebview?.api.open_folder(statusMessage.folder || "")}
            >
              Open Folder
            </button>
          )}
        </div>
      )}

      {/* HTML drag overlay */}
      {dragActive && (
        <div 
          className="drag-overlay"
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <Upload className="drag-icon" size={64} style={{ color: "var(--accent-teal)" }} />
          <h2>Drop document to load it in the workspace</h2>
        </div>
      )}
    </div>
  );
}
