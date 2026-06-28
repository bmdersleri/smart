import fs from 'fs';
import path from 'path';

function walk(dir, callback) {
  if (!fs.existsSync(dir)) return;
  fs.readdirSync(dir).forEach(f => {
    let dirPath = path.join(dir, f);
    let isDirectory = fs.statSync(dirPath).isDirectory();
    isDirectory ? walk(dirPath, callback) : callback(dirPath);
  });
}

const replacements = [
  {
    from: /bg-gray-900 border border-gray-800 rounded-xl/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl"
  },
  {
    from: /bg-gray-900 border border-gray-800 rounded-lg/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl"
  },
  {
    from: /bg-gray-900 border border-gray-700 rounded-2xl/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl"
  },
  {
    from: /bg-gray-900 border border-gray-700 rounded-lg/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl"
  },
  {
    from: /bg-gray-900 border border-gray-800/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5"
  },
  {
    from: /bg-gray-900 border border-gray-700/g,
    to: "bg-gray-900/40 backdrop-blur-xl border border-white/5"
  },
  {
    from: /bg-gray-900 rounded-2xl border border-gray-800/g,
    to: "bg-gray-900/40 backdrop-blur-xl rounded-2xl border border-white/5"
  },
  {
    from: /bg-gray-900 rounded-xl border border-gray-800/g,
    to: "bg-gray-900/40 backdrop-blur-xl rounded-2xl border border-white/5"
  },
  {
    from: /hover:bg-gray-800 hover:text-white/g,
    to: "hover:bg-white/5 hover:text-white"
  },
  {
    from: /hover:bg-gray-800/g,
    to: "hover:bg-white/5"
  },
  {
    from: /focus:border-blue-500/g,
    to: "focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50"
  },
  {
    from: /text-blue-500/g,
    to: "text-cyan-400"
  },
  {
    from: /text-blue-400/g,
    to: "text-cyan-400"
  },
  {
    from: /bg-blue-600 text-white/g,
    to: "bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30"
  }
];

const processFile = (filePath) => {
  if (filePath.endsWith('.tsx') || filePath.endsWith('.ts')) {
    let content = fs.readFileSync(filePath, 'utf8');
    let newContent = content;

    // Apply specific replacements first
    replacements.forEach(r => {
      newContent = newContent.replace(r.from, r.to);
    });

    // Fallback for remaining bg-gray-900 that don't have transparency already
    // but only if it's a tailwind class (e.g. following a quote or space)
    newContent = newContent.replace(/bg-gray-900(?!\/)/g, "bg-gray-900/40 backdrop-blur-xl");

    if (content !== newContent) {
      fs.writeFileSync(filePath, newContent);
      console.log(`Updated ${filePath}`);
    }
  }
};

walk(path.join(process.cwd(), 'src', 'pages'), processFile);
walk(path.join(process.cwd(), 'src', 'components'), processFile);
