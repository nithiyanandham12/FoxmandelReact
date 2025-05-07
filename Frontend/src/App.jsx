import React, { useState, useEffect } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import {
  Box,
  Container,
  Stepper,
  Step,
  StepLabel,
  Typography,
  Paper,
  Button,
  LinearProgress,
  TextField,
  Grid,
  AppBar,
  Toolbar,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  CircularProgress,
  Card,
  CardContent,
  Link,
  Tabs,
  Tab,
  Alert,
  Snackbar,
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  Spellcheck as SpellcheckIcon,
  Description as DescriptionIcon,
  Download as DownloadIcon,
  ArrowBack as ArrowBackIcon,
  ArrowForward as ArrowForwardIcon,
  NavigateNext as NavigateNextIcon,
  Report as ReportIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import axios from 'axios';
import Markdown from 'markdown-to-jsx';
import './App.css';

// Step labels
const steps = ['Upload Document', 'Quality Check', 'Generate Report', 'Download Results'];

// Create theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  typography: {
    fontFamily: 'Roboto, Arial, sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 500,
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 500,
    },
    h3: {
      fontSize: '1.8rem',
      fontWeight: 500,
    },
  },
});

// API base URL
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? '' // Empty string for production since we'll use relative paths when deployed together
  : 'http://localhost:8000';

function App() {
  // State variables
  const [activeStep, setActiveStep] = useState(0);
  const [sessionId, setSessionId] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [processingStatus, setProcessingStatus] = useState({
    status: '',
    message: '',
    progress: 0,
    currentStage: '',
    totalPages: 0,
    processedPages: 0
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [pageData, setPageData] = useState({
    rawText: '',
    translatedText: '',
    editedText: ''
  });
  const [pageImage, setPageImage] = useState('');
  const [tabValue, setTabValue] = useState(0);
  const [reportResult, setReportResult] = useState('');
  const [clientName, setClientName] = useState('');
  const [openAlert, setOpenAlert] = useState(false);
  const [alertMessage, setAlertMessage] = useState('');
  const [alertSeverity, setAlertSeverity] = useState('info');
  const [pollingInterval, setPollingInterval] = useState(null);
  
  // Handle file upload
  const handleFileChange = (event) => {
    setFile(event.target.files[0]);
  };
  
  // Upload file and start processing
  const handleUpload = async () => {
    if (!file) {
      showAlert('Please select a file to upload', 'error');
      return;
    }
    
    setUploading(true);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/upload`, formData);
      setSessionId(response.data.session_id);
      showAlert('File uploaded successfully', 'success');
      startStatusPolling(response.data.session_id);
    } catch (error) {
      console.error('Error uploading file:', error);
      showAlert('Error uploading file: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setUploading(false);
    }
  };
  
  // Poll for processing status
  const startStatusPolling = (id) => {
    // Clear any existing interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }
    
    // Start new polling
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/status/${id}`);
        const status = response.data;
        
        setProcessingStatus({
          status: status.status,
          message: status.message,
          progress: status.progress,
          currentStage: status.current_stage,
          totalPages: status.total_pages,
          processedPages: status.processed_pages
        });
        
        // Move to next step if processing is complete
        if (status.status === 'ready_for_review') {
          clearInterval(interval);
          setPollingInterval(null);
          loadPageData(id, 1);
          setActiveStep(1); // Move to Quality Check step
        } else if (status.status === 'completed' || status.status === 'completed_with_warning') {
          clearInterval(interval);
          setPollingInterval(null);
          fetchReportResult(id);
          setActiveStep(3); // Move to Download Results step
        } else if (status.status === 'error') {
          clearInterval(interval);
          setPollingInterval(null);
          showAlert(`Error: ${status.message}`, 'error');
        }
      } catch (error) {
        console.error('Error fetching status:', error);
        showAlert('Error fetching processing status', 'error');
        clearInterval(interval);
        setPollingInterval(null);
      }
    }, 2000);
    
    setPollingInterval(interval);
  };
  
  // Load page data for review
  const loadPageData = async (id, pageNum) => {
    try {
      // Fetch page data
      const pageResponse = await axios.get(`${API_BASE_URL}/pages/${id}/${pageNum}`);
      const imageResponse = await axios.get(`${API_BASE_URL}/image/${id}/${pageNum}`);
      
      setPageData({
        rawText: pageResponse.data.raw_text,
        translatedText: pageResponse.data.translated_text,
        editedText: pageResponse.data.translated_text // Default to translated text
      });
      
      setPageImage(imageResponse.data.image);
      setCurrentPage(pageNum);
    } catch (error) {
      console.error('Error loading page data:', error);
      showAlert('Error loading page data', 'error');
    }
  };
  
  // Update page text
  const handleTextUpdate = async () => {
    try {
      await axios.put(`${API_BASE_URL}/update-page/${sessionId}`, {
        page_number: currentPage,
        edited_text: tabValue === 0 ? pageData.translatedText : pageData.rawText
      });
      
      showAlert('Page updated successfully', 'success');
    } catch (error) {
      console.error('Error updating page:', error);
      showAlert('Error updating page', 'error');
    }
  };
  
  // Generate report
  const handleGenerateReport = async () => {
    try {
      await axios.post(`${API_BASE_URL}/generate-report/${sessionId}`, {
        session_id: sessionId,
        client_name: clientName
      });
      
      showAlert('Report generation started', 'info');
      startStatusPolling(sessionId);
      setActiveStep(2); // Move to Generate Report step
    } catch (error) {
      console.error('Error starting report generation:', error);
      showAlert('Error starting report generation', 'error');
    }
  };
  
  // Fetch report result
  const fetchReportResult = async (id) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/status/${id}`);
      if (response.data.status === 'completed' || response.data.status === 'completed_with_warning') {
        setReportResult(response.data.final_output || 'Report generated successfully!');
      }
    } catch (error) {
      console.error('Error fetching report result:', error);
    }
  };
  
  // Download report
  const handleDownload = async (fileType) => {
    try {
      // Use window.open for direct download
      window.open(`${API_BASE_URL}/download/${sessionId}/${fileType}`, '_blank');
    } catch (error) {
      console.error(`Error downloading ${fileType} file:`, error);
      showAlert(`Error downloading ${fileType} file`, 'error');
    }
  };
  
  // Show alert message
  const showAlert = (message, severity = 'info') => {
    setAlertMessage(message);
    setAlertSeverity(severity);
    setOpenAlert(true);
  };
  
  // Handle tab change
  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };
  
  // Navigate pages
  const handlePrevPage = () => {
    if (currentPage > 1) {
      loadPageData(sessionId, currentPage - 1);
    }
  };
  
  const handleNextPage = () => {
    if (currentPage < processingStatus.totalPages) {
      loadPageData(sessionId, currentPage + 1);
    }
  };
  
  // Handle text editing
  const handleTextEdit = (event) => {
    if (tabValue === 0) {
      setPageData({ ...pageData, translatedText: event.target.value });
    } else {
      setPageData({ ...pageData, rawText: event.target.value });
    }
  };
  
  // Reset the application
  const handleReset = () => {
    setActiveStep(0);
    setSessionId('');
    setFile(null);
    setProcessingStatus({
      status: '',
      message: '',
      progress: 0,
      currentStage: '',
      totalPages: 0,
      processedPages: 0
    });
    setCurrentPage(1);
    setPageData({
      rawText: '',
      translatedText: '',
      editedText: ''
    });
    setPageImage('');
    setTabValue(0);
    setReportResult('');
    setClientName('');
    
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  };
  
  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);
  
  // Render step content
  const getStepContent = (step) => {
    switch (step) {
      case 0: // Upload Document
        return (
          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <input
              accept="application/pdf"
              style={{ display: 'none' }}
              id="raised-button-file"
              type="file"
              onChange={handleFileChange}
            />
            <label htmlFor="raised-button-file">
              <Button
                variant="contained"
                component="span"
                startIcon={<CloudUploadIcon />}
                sx={{ mb: 2 }}
              >
                Select PDF File
              </Button>
            </label>
            
            {file && (
              <Typography variant="body1" sx={{ mt: 2 }}>
                Selected file: {file.name}
              </Typography>
            )}
            
            <Box sx={{ mt: 3 }}>
              <Button
                variant="contained"
                color="primary"
                onClick={handleUpload}
                disabled={!file || uploading}
                sx={{ minWidth: 200 }}
              >
                {uploading ? (
                  <CircularProgress size={24} color="inherit" />
                ) : (
                  'Upload & Process'
                )}
              </Button>
            </Box>
            
            {processingStatus.status && (
              <Box sx={{ mt: 4, width: '100%' }}>
                <LinearProgress
                  variant="determinate"
                  value={processingStatus.progress * 100}
                  sx={{ height: 10, borderRadius: 5 }}
                />
                <Typography variant="body2" sx={{ mt: 1 }}>
                  {processingStatus.message}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {processingStatus.processedPages} / {processingStatus.totalPages} pages processed
                </Typography>
              </Box>
            )}
          </Box>
        );
        
      case 1: // Quality Check
        return (
          <Box sx={{ mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              Review and Edit OCR Results
            </Typography>
            
            <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Button
                onClick={handlePrevPage}
                disabled={currentPage <= 1}
                startIcon={<ArrowBackIcon />}
              >
                Previous
              </Button>
              
              <Typography>
                Page {currentPage} of {processingStatus.totalPages}
              </Typography>
              
              <Button
                onClick={handleNextPage}
                disabled={currentPage >= processingStatus.totalPages}
                endIcon={<ArrowForwardIcon />}
              >
                Next
              </Button>
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={5}>
                <Paper sx={{ p: 2, mb: 2, height: '500px', overflow: 'auto' }}>
                  <Typography variant="subtitle1" gutterBottom>
                    PDF Page
                  </Typography>
                  {pageImage ? (
                    <img 
                      src={`data:image/png;base64,${pageImage}`} 
                      alt={`Page ${currentPage}`}
                      style={{ width: '100%' }}
                    />
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                      <CircularProgress />
                    </Box>
                  )}
                </Paper>
              </Grid>
              
              <Grid item xs={12} md={7}>
                <Paper sx={{ p: 2, mb: 2, height: '500px' }}>
                  <Tabs value={tabValue} onChange={handleTabChange}>
                    <Tab label="Translated Text" />
                    <Tab label="Raw OCR Text" />
                  </Tabs>
                  
                  <Box sx={{ mt: 2, height: 'calc(100% - 70px)' }}>
                    <TextField
                      label={tabValue === 0 ? "Translated Text (Editable)" : "Raw OCR Text (Editable)"}
                      multiline
                      fullWidth
                      rows={18}
                      value={tabValue === 0 ? pageData.translatedText : pageData.rawText}
                      onChange={handleTextEdit}
                      variant="outlined"
                    />
                  </Box>
                </Paper>
                
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 2 }}>
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={handleTextUpdate}
                  >
                    Save Changes
                  </Button>
                  
                  <Button
                    variant="contained"
                    color="secondary"
                    endIcon={<NavigateNextIcon />}
                    onClick={() => setActiveStep(2)}
                  >
                    Proceed to Report Generation
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Box>
        );
        
      case 2: // Generate Report
        return (
          <Box sx={{ mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              Generate Report
            </Typography>
            
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="body1" paragraph>
                Enter client information for the report and click "Generate" to create your legal document report.
              </Typography>
              
              <TextField
                label="Client Name"
                fullWidth
                margin="normal"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                helperText="This will appear in the report header"
              />
              
              <Box sx={{ mt: 3, textAlign: 'center' }}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleGenerateReport}
                  disabled={processingStatus.status === 'generating_report'}
                  startIcon={processingStatus.status === 'generating_report' ? <CircularProgress size={20} /> : <ReportIcon />}
                  sx={{ minWidth: 200 }}
                >
                  {processingStatus.status === 'generating_report' ? 'Generating...' : 'Generate Report'}
                </Button>
              </Box>
              
              {processingStatus.status === 'generating_report' && (
                <Box sx={{ mt: 4, width: '100%' }}>
                  <LinearProgress
                    variant="determinate"
                    value={processingStatus.progress * 100}
                    sx={{ height: 10, borderRadius: 5 }}
                  />
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    {processingStatus.message}
                  </Typography>
                </Box>
              )}
            </Paper>
          </Box>
        );
        
        case 3: // Download Results
        return (
          <Box sx={{ mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              Report Generated Successfully
            </Typography>
            
            <Paper sx={{ p: 3, mb: 3 }}>
              <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
                <Button
                  variant="contained"
                  startIcon={<DownloadIcon />}
                  onClick={() => handleDownload('markdown')}
                >
                  Download Markdown
                </Button>
                
                <Button
                  variant="contained"
                  color="primary"
                  startIcon={<DownloadIcon />}
                  onClick={() => handleDownload('docx')}
                >
                  Download Word Document
                </Button>
              </Box>
              
              <Typography variant="h6" gutterBottom>
                Report Preview:
              </Typography>
              
              <Paper 
                sx={{ 
                  p: 3, 
                  mt: 2, 
                  maxHeight: '500px', 
                  overflow: 'auto', 
                  backgroundColor: '#f8f9fa' 
                }}
              >
                {reportResult ? (
                  <Markdown>
                    {reportResult}
                  </Markdown>
                ) : (
                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>Loading report content...</Typography>
                  </Box>
                )}
              </Paper>
            </Paper>
            
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={handleReset}
              >
                Process Another Document
              </Button>
            </Box>
          </Box>
        );
      
        
      default:
        return 'Unknown step';
    }
  };
  
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Fox Mandal OCR-AI | Legal Document Processor
            </Typography>
          </Toolbar>
        </AppBar>
        
        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          <Paper sx={{ p: 3 }}>
            <Stepper activeStep={activeStep} alternativeLabel>
              {steps.map((label) => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>
            
            <Box sx={{ mt: 4 }}>
              {getStepContent(activeStep)}
            </Box>
          </Paper>
          
          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="textSecondary">
              © {new Date().getFullYear()} Fox Mandal & Associates. All rights reserved.
            </Typography>
          </Box>
        </Container>
      </Box>
      
      <Snackbar 
        open={openAlert} 
        autoHideDuration={6000} 
        onClose={() => setOpenAlert(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={() => setOpenAlert(false)} 
          severity={alertSeverity} 
          sx={{ width: '100%' }}
        >
          {alertMessage}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  );
}

export default App;
