import React from 'react';

interface SmartPluginIconProps {
  className?: string;
  size?: number;
}

export const SmartPluginIcon: React.FC<SmartPluginIconProps> = ({ 
  className = '', 
  size = 64 
}) => {
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox="0 0 64 64" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="pluginGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
        <linearGradient id="pluginGradientLight" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>
      
      <circle cx="32" cy="32" r="30" fill="url(#pluginGradient)" opacity="0.1" />
      <circle cx="32" cy="32" r="28" fill="url(#pluginGradient)" opacity="0.15" />
      
      <path 
        d="M20 18 
           C20 15.7909 21.7909 14 24 14 
           H28 
           C28 11.7909 29.7909 10 32 10 
           C34.2091 10 36 11.7909 36 14 
           H40 
           C42.2091 14 44 15.7909 44 18 
           V22 
           C46.2091 22 48 23.7909 48 26 
           C48 28.2091 46.2091 30 44 30 
           V34 
           C46.2091 34 48 35.7909 48 38 
           C48 40.2091 46.2091 42 44 42 
           V46 
           C44 48.2091 42.2091 50 40 50 
           H36 
           C36 52.2091 34.2091 54 32 54 
           C29.7909 54 28 52.2091 28 50 
           H24 
           C21.7909 50 20 48.2091 20 46 
           V42 
           C17.7909 42 16 40.2091 16 38 
           C16 35.7909 17.7909 34 20 34 
           V30 
           C17.7909 30 16 28.2091 16 26 
           C16 23.7909 17.7909 22 20 22 
           V18Z" 
        fill="url(#pluginGradient)"
        filter="url(#glow)"
      />
      
      <path 
        d="M22 20 
           C22 18.8954 22.8954 18 24 18 
           H28.5 
           C28.5 16.8954 29.3954 16 30.5 16 
           C31.6046 16 32.5 16.8954 32.5 18 
           H37 
           C38.1046 18 39 18.8954 39 20 
           V23.5 
           C40.1046 23.5 41 24.3954 41 25.5 
           C41 26.6046 40.1046 27.5 39 27.5 
           V31.5 
           C40.1046 31.5 41 32.3954 41 33.5 
           C41 34.6046 40.1046 35.5 39 35.5 
           V39 
           C39 40.1046 38.1046 41 37 41 
           H32.5 
           C32.5 42.1046 31.6046 43 30.5 43 
           C29.3954 43 28.5 42.1046 28.5 41 
           H24 
           C22.8954 41 22 40.1046 22 39 
           V35.5 
           C20.8954 35.5 20 34.6046 20 33.5 
           C20 32.3954 20.8954 31.5 22 31.5 
           V27.5 
           C20.8954 27.5 20 26.6046 20 25.5 
           C20 24.3954 20.8954 23.5 22 23.5 
           V20Z" 
        fill="url(#pluginGradientLight)"
        opacity="0.6"
      />
      
      <rect x="26" y="26" width="12" height="12" rx="2" fill="white" opacity="0.9" />
      <rect x="28" y="28" width="8" height="8" rx="1" fill="url(#pluginGradient)" />
      
      <rect x="29" y="24" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="33" y="24" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="29" y="38" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="33" y="38" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="24" y="29" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="24" y="33" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="38" y="29" width="2" height="2" fill="white" opacity="0.7" />
      <rect x="38" y="33" width="2" height="2" fill="white" opacity="0.7" />
      
      <circle cx="18" cy="18" r="2" fill="white" opacity="0.4" />
      <circle cx="46" cy="18" r="1.5" fill="white" opacity="0.3" />
      <circle cx="18" cy="46" r="1.5" fill="white" opacity="0.3" />
      <circle cx="46" cy="46" r="2" fill="white" opacity="0.4" />
    </svg>
  );
};

export default SmartPluginIcon;
