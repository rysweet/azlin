/**
 * TmuxTerminalDisplay Component
 *
 * Terminal display with line highlighting for watch mode.
 * Highlights changed lines (yellow) and new lines (green).
 *
 * Philosophy:
 * - Single responsibility: Terminal content display with highlighting
 * - Self-contained with clear props interface
 * - Zero-BS: Real highlighting with real color differentiation
 */

import { Paper, Typography, Box } from '@mui/material';
import { useRef, useEffect } from 'react';

export interface LineHighlight {
  lineNumber: number;
  type: 'changed' | 'new';
}

export interface TmuxTerminalDisplayProps {
  lines: string[];
  highlights?: LineHighlight[];
  autoScroll?: boolean;
  loading?: boolean;
}

export function TmuxTerminalDisplay({
  lines,
  highlights = [],
  autoScroll = false,
  loading = false,
}: TmuxTerminalDisplayProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when content changes
  useEffect(() => {
    if (autoScroll && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  const getLineStyle = (lineNumber: number): React.CSSProperties => {
    const highlight = highlights.find(h => h.lineNumber === lineNumber);

    if (!highlight) {
      return {};
    }

    // Changed lines: yellow background
    if (highlight.type === 'changed') {
      return {
        backgroundColor: 'rgba(255, 255, 0, 0.15)',
        borderLeft: '3px solid #ffeb3b',
        paddingLeft: '8px',
      };
    }

    // New lines: green background
    if (highlight.type === 'new') {
      return {
        backgroundColor: 'rgba(0, 255, 0, 0.10)',
        borderLeft: '3px solid #4caf50',
        paddingLeft: '8px',
      };
    }

    return {};
  };

  return (
    <Paper
      ref={scrollContainerRef}
      sx={{
        p: 2,
        bgcolor: 'black',
        color: '#00ff00',
        fontFamily: 'monospace',
        fontSize: '14px',
        minHeight: 400,
        maxHeight: '60vh',
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        position: 'relative',
      }}
    >
      {lines && lines.length > 0 ? (
        lines.map((line, idx) => (
          <Box
            key={idx}
            sx={{
              ...getLineStyle(idx),
              transition: 'background-color 0.3s ease, border-left 0.3s ease',
            }}
          >
            {line || ' '}
          </Box>
        ))
      ) : (
        !loading && (
          <Typography color="grey.500">
            No content captured yet. Click Refresh to load.
          </Typography>
        )
      )}
    </Paper>
  );
}

export default TmuxTerminalDisplay;
