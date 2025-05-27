import streamlit as st
import pandas as pd

# Page config
st.set_page_config(
    page_title="CSV Data Slicer",
    page_icon="📊",
    layout="wide"
)

st.title("📊 CSV Data Slicer")
st.markdown("Upload a CSV file and explore your data interactively")

# File uploader
uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file is not None:
    # Load data
    df = pd.read_csv(uploaded_file)
    
    # Filter out empty rows - rows where all values are NaN or empty strings
    initial_rows = len(df)
    df = df.dropna(how='all')  # Remove rows where all columns are NaN
    df = df[~df.astype(str).apply(lambda x: x.str.strip().eq('')).all(axis=1)]  # Remove rows where all columns are empty strings
    df = df.reset_index(drop=True)  # Reset index after filtering
    
    rows_removed = initial_rows - len(df)

    
    # Sidebar for controls
    st.sidebar.header("🎛️ Data Controls")
    
    # Display basic info
    st.sidebar.subheader("Dataset Info")
    st.sidebar.write(f"**Rows:** {df.shape[0]:,}")
    st.sidebar.write(f"**Columns:** {df.shape[1]}")
    
    # Column selection
    all_columns = df.columns.tolist()
    selected_columns = st.sidebar.multiselect(
        "Select columns to display:",
        all_columns,
        default=all_columns[:5] if len(all_columns) > 5 else all_columns
    )
    
    if selected_columns:
        filtered_df = df[selected_columns].copy()
        
        # Dynamic filters for each selected column
        st.sidebar.subheader("🔍 Filters")
        
        filters = {}
        for col in selected_columns:
            if df[col].dtype in ['object', 'string']:
                # Categorical filter
                unique_values = df[col].unique()
                if len(unique_values) <= 20:  # Only show multiselect for reasonable number of options
                    selected_values = st.sidebar.multiselect(
                        f"Filter {col}:",
                        options=unique_values,
                        default=unique_values
                    )
                    filters[col] = selected_values
                else:
                    # Text search for columns with too many unique values
                    search_term = st.sidebar.text_input(f"Search in {col}:")
                    if search_term:
                        filters[col] = search_term
            
            elif df[col].dtype in ['int64', 'float64']:
                # Numeric filter
                min_val = float(df[col].min())
                max_val = float(df[col].max())
                if min_val != max_val:
                    selected_range = st.sidebar.slider(
                        f"Filter {col}:",
                        min_value=min_val,
                        max_value=max_val,
                        value=(min_val, max_val),
                        step=(max_val - min_val) / 100
                    )
                    filters[col] = selected_range
        
        # Apply filters
        for col, filter_value in filters.items():
            if df[col].dtype in ['object', 'string']:
                if isinstance(filter_value, list):
                    filtered_df = filtered_df[filtered_df[col].isin(filter_value)]
                else:  # text search
                    filtered_df = filtered_df[filtered_df[col].str.contains(filter_value, na=False, case=False)]
            elif df[col].dtype in ['int64', 'float64']:
                filtered_df = filtered_df[
                    (filtered_df[col] >= filter_value[0]) & 
                    (filtered_df[col] <= filter_value[1])
                ]
        
        # Main content area
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(f"📋 Data View ({len(filtered_df):,} rows)")
            st.dataframe(filtered_df, use_container_width=True, height=500)
        
        with col2:
            st.subheader("📈 Quick Stats")
            
            # Show stats for numeric columns
            numeric_cols = filtered_df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                stats_df = filtered_df[numeric_cols].describe()
                st.dataframe(stats_df, use_container_width=True)
            
            # Show value counts for categorical columns
            categorical_cols = filtered_df.select_dtypes(include=['object', 'string']).columns
            if len(categorical_cols) > 0:
                selected_cat_col = st.selectbox("Show value counts for:", categorical_cols)
                if selected_cat_col:
                    value_counts = filtered_df[selected_cat_col].value_counts().head(10)
                    st.dataframe(value_counts.to_frame('Count'), use_container_width=True)
            
            # Summary section
            st.subheader("📊 Summary")
            st.write(f"**Total rows after filtering:** {len(filtered_df):,}")
            st.write(f"**Columns displayed:** {len(selected_columns)}")
            
            # Download filtered data
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download filtered data as CSV",
                data=csv,
                file_name="filtered_data.csv",
                mime="text/csv"
            )
            
            # Show data types
            st.subheader("🏷️ Data Types")
            dtypes_df = pd.DataFrame({
                'Column': filtered_df.columns,
                'Type': filtered_df.dtypes.astype(str)
            })
            st.dataframe(dtypes_df, hide_index=True)

else:
    st.info("👆 Please upload a CSV file to get started")
    
    # Show example of what the app can do
    st.subheader("What this app can do:")
    st.markdown("""
    - 📁 **Upload CSV files** and instantly explore them
    - 🧹 **Automatically removes empty rows** to prevent crashes
    - 🔍 **Filter data** by any column (text search, dropdowns, sliders)
    - 📈 **View statistics** and summaries
    - 📥 **Download filtered data** as new CSV files
    - 🎛️ **Interactive controls** that update everything in real-time
    """)