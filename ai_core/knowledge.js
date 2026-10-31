"use strict";

// Small, original starter knowledge for local JARVIS experiments.
// This is searchable reference text, not trained model weights.
module.exports = [
  {
    id: "jarvis-local-model",
    topic: "JARVIS local AI model",
    tags: ["jarvis", "ai", "model", "training", "local", "मॉडल", "प्रशिक्षण"],
    text:
      "JARVIS ka experimental language model local machine par randomly initialized " +
      "weights se train hota hai. Chhota model learning pipeline samjhane ke liye hai; " +
      "ise ChatGPT-level ya general-purpose intelligence nahi kehna chahiye.",
    source: "Original project note",
  },
  {
    id: "training-vs-memory",
    topic: "Training aur memory ka farq",
    tags: ["training", "memory", "knowledge", "checkpoint", "प्रशिक्षण", "याददाश्त"],
    text:
      "Training neural model ke weights badalti hai aur checkpoint banati hai. " +
      "Memory ya saved documents alag local data hote hain; unhe save karne se " +
      "model ke weights apne aap train nahi hote.",
    source: "Original project note",
  },
  {
    id: "dataset-permission",
    topic: "Local dataset safety",
    tags: ["dataset", "text", "permission", "license", "data", "डेटासेट", "अनुमति"],
    text:
      "Training ke liye wahi text use karo jo tumne likha ho, jiske use ki permission " +
      "ho, ya jo suitable license ke saath available ho. Private files ko bina approval " +
      "import ya train nahi karna chahiye.",
    source: "Original project note",
  },
  {
    id: "safe-desktop-actions",
    topic: "Safe desktop assistant actions",
    tags: ["assistant", "desktop", "commands", "safety", "automation", "सुरक्षा"],
    text:
      "Desktop assistant ko approved commands ki allow-list use karni chahiye. " +
      "Generated text ko seedha shell command ke roop mein execute nahi karna chahiye; " +
      "important ya destructive actions ko validate aur confirm karna chahiye.",
    source: "Original project note",
  },
  {
    id: "hindi-utf8",
    topic: "Hindi aur UTF-8 text",
    tags: ["hindi", "unicode", "utf-8", "hinglish", "देवनागरी"],
    text:
      "Hindi Devanagari aur Hinglish ko Unicode text ke roop mein UTF-8 encoding ke " +
      "saath store karna chahiye. Text ko decode karte waqt invalid bytes ko handle " +
      "karna aur original meaning ko preserve karna zaroori hai.",
    source: "Original project note",
  },
];
